import os
import asyncio
from typing import Dict, Any, List, Literal
from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from core.models import TaskStatus, ProjectState
from agents.agents import ResearcherAgent, AgentGraphState
from agents.orchestrator.orchestrator import OrchestratorAgent
from agents.crews.coding_crew.graph import build_coding_crew_graph
from agents.crews.coding_crew.nodes import _sandbox as coding_sandbox

# [Phase 3 New] 引入状态切片工具
from core.utils import slice_state_for_crew

def load_prompt_file(path: str) -> str:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: return f.read().strip()
    return ""

def common_input_mapper(state: AgentGraphState) -> Dict[str, Any]:
    project = state["project_state"]
    active_node = project.get_active_node()
    if not active_node: return {}
    return {
        "task_id": project.task_id,
        "user_input": project.root_node.instruction,
        "full_chat_history": active_node.local_history,
        "current_instruction": active_node.instruction,
        "iteration_count": 0,
        "review_status": "pending",
        "image_artifacts": [] 
    }

# --- Phase 3 New: Sync Gate & Aggregator Nodes ---

async def sync_gate_node(state: AgentGraphState) -> Dict[str, Any]:
    """
    [Phase 3] 同步门：所有并行分支在此汇聚。
    LangGraph 的 Graph 结构会自动等待所有分支完成才进入此节点 (Fan-in)。
    在此处我们可以做额外的完整性检查。
    """
    project = state["project_state"]
    print(f"⛩️ [Sync Gate] Parallel branches merged. Clock: {project.vector_clock}")
    
    # 这里可以添加逻辑：检查是否所有被派出的 Agent 都真正更新了状态
    # 目前主要作为汇聚点存在
    return {"project_state": project}

async def call_aggregator(state: AgentGraphState) -> Dict[str, Any]:
    """
    [Phase 3] 聚合器：将并行 Agent 的结果“压平”并生成统一摘要。
    """
    project: ProjectState = state["project_state"]
    active_node = project.get_active_node()
    next_step = project.next_step or {}
    
    parallel_agents = next_step.get("parallel_agents", [])
    if isinstance(parallel_agents, str): parallel_agents = [parallel_agents]
    
    print(f"🏁 [Aggregator] Summarizing outputs from: {parallel_agents}")
    
    ensemble_summary = []
    
    # 1. 收集各分支摘要
    for agent_name in parallel_agents:
        # 这里简化处理：假设各 Agent 在执行完后，将其最后的一句摘要留在了某个地方
        # 或者我们检查 code_blocks / artifacts 的更新情况
        
        agent_role = agent_name.replace("_crew", "").capitalize()
        ensemble_summary.append(f"[{agent_role}]: Task Executed.") 
        
        # 如果是 Coding Crew，检查代码更新
        if agent_name == "coding_crew" and project.code_blocks:
            ensemble_summary[-1] += f" Updated {len(project.code_blocks)} code files."
            
    # 2. 生成合奏报告
    final_digest = " | ".join(ensemble_summary)
    
    # 3. 更新 Active Node 上下文，供 Orchestrator 下一轮读取
    if active_node:
        active_node.semantic_summary = f"Parallel Execution Result: {final_digest}"
        # 记录一条系统消息，避免 Token 爆炸
        active_node.local_history.append({
            "role": "system",
            "parts": [{"text": f"✅ [Aggregator] Parallel execution finished. Summary: {final_digest}"}]
        })
    
    # 4. 清理 Next Step 状态，防止死循环
    project.next_step = None
    
    return {"project_state": project}

# --- Routing Logic Rewrite ---

def route_next_step(state: AgentGraphState) -> Any:
    """
    [Phase 3 Upgrade] 支持并行路由
    返回列表 List[str] 表示并行触发多个节点。
    """
    project = state["project_state"]
    decision = project.router_decision
    
    if decision == "finish": return "end"
    if decision == "human": return "orchestrator" 
    if decision == "tool": return "orchestrator" 
    
    next_step = project.next_step
    if not next_step: return "orchestrator"
    
    # 检查并行列表
    parallel_agents = next_step.get("parallel_agents")
    
    # 如果是列表且非空，返回列表以触发并行 (Fan-out)
    if isinstance(parallel_agents, list) and parallel_agents:
        valid_routes = [a for a in parallel_agents if a in ["researcher", "coding_crew", "data_crew", "content_crew"]]
        if valid_routes:
            print(f"🔀 [Router] Fan-out to: {valid_routes}")
            return valid_routes
            
    # 单一目标兼容
    agent_name = next_step.get("agent_name", "").lower()
    if agent_name in ["researcher", "coding_crew", "data_crew", "content_crew"]:
        return agent_name
        
    return "orchestrator"

# --- Graph Builder ---

def build_agent_workflow(
    rotator: GeminiKeyRotator, 
    memory_tool: VectorMemoryTool, 
    search_tool: GoogleSearchTool,
    checkpointer: Any = None 
) -> StateGraph:
    
    workflow = StateGraph(AgentGraphState) # 显式初始化
    
    orch_prompt = load_prompt_file("agents/orchestrator/prompts/orchestrator.md")
    res_prompt = "Role: Research Assistant. Summarize search results into JSON."
    
    orchestrator = OrchestratorAgent(rotator, orch_prompt)
    researcher = ResearcherAgent(rotator, memory_tool, search_tool, res_prompt)
    
    coding_app = build_coding_crew_graph(rotator)
    
    # --- Orchestrator Wrapper ---
    async def orchestrator_node(state: AgentGraphState):
        result = orchestrator.run(state)
        project_state = result["project_state"]
        
        # [Speculative] Trigger Side Effects
        next_step = project_state.next_step
        if next_step:
            # 兼容旧的 agent_name 和新的 parallel_agents
            targets = next_step.get("parallel_agents") or [next_step.get("agent_name")]
            spec_queries = next_step.get("speculative_queries")
            
            if "coding_crew" in targets:
                print("🔥 [Workflow] Predicting Coding Task: Triggering Sandbox Warm-up...")
                asyncio.create_task(async_warmup_sandbox())

            if spec_queries:
                print(f"⚡️ [Workflow] Speculative Search triggered for: {spec_queries}")
                for q in spec_queries:
                    asyncio.create_task(async_prefetch_search(q, search_tool, project_state))
        
        return result

    async def async_warmup_sandbox():
        try:
            coding_sandbox.warm_up()
        except Exception as e:
            print(f"Warmup failed: {e}")

    async def async_prefetch_search(query: str, tool: GoogleSearchTool, ps: ProjectState):
        try:
            res = await tool.search(query)
            if res:
                ps.prefetch_cache[query] = res
        except Exception as e:
            print(f"   ❌ [Prefetch] Failed for '{query}': {e}")

    # --- Nodes ---
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("researcher", researcher.run) 
    
    # [Worker Wrappers]
    async def call_coding(state: AgentGraphState):
        print(f"🔄 [Subtree] Entering Coding Crew...")
        # [Phase 1] Slicing (暂保留逻辑兼容)
        # crew_slice = slice_state_for_crew(state["project_state"], "coding_crew")
        
        res = await coding_app.ainvoke(common_input_mapper(state))
        
        project = state["project_state"]
        code = res.get("generated_code", "")
        images = res.get("image_artifacts", [])
        
        if code: project.code_blocks["coding_crew"] = code
        if images: project.artifacts["images"] = images
        
        project.vector_clock["coding_crew"] = project.vector_clock.get("coding_crew", 0) + 1
        
        # Active Node status update skipped here, moved to Aggregator logic mainly
        return {"project_state": project}

    async def call_data(state: AgentGraphState):
        project = state["project_state"]
        project.vector_clock["data_crew"] = project.vector_clock.get("data_crew", 0) + 1
        return {"project_state": project} 

    async def call_content(state: AgentGraphState):
        project = state["project_state"]
        project.vector_clock["content_crew"] = project.vector_clock.get("content_crew", 0) + 1
        return {"project_state": project}

    workflow.add_node("coding_crew", call_coding)
    workflow.add_node("data_crew", call_data)
    workflow.add_node("content_crew", call_content)
    
    # [Phase 3 New Nodes]
    workflow.add_node("sync_gate", sync_gate_node)
    workflow.add_node("aggregator", call_aggregator)
    
    # --- Edges & Topology ---
    
    workflow.set_entry_point("orchestrator")
    
    # 1. Orchestrator -> [Agents...] (Fan-out via route_next_step)
    workflow.add_conditional_edges(
        "orchestrator", 
        route_next_step, 
        {
            "researcher": "researcher",
            "coding_crew": "coding_crew",
            "data_crew": "data_crew",
            "content_crew": "content_crew",
            "orchestrator": "orchestrator", 
            "end": END
        }
    )
    
    # 2. Agents -> Sync Gate (Fan-in)
    worker_nodes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    for node in worker_nodes:
        workflow.add_edge(node, "sync_gate")
        
    # 3. Sync Gate -> Aggregator
    workflow.add_edge("sync_gate", "aggregator")
    
    # 4. Aggregator -> Orchestrator (Loop back)
    workflow.add_edge("aggregator", "orchestrator")
    
    return workflow.compile(checkpointer=checkpointer, interrupt_before=[])
