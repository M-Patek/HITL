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
    project = state["project_state"]
    # 简单的同步点
    return {"project_state": project}

async def call_aggregator(state: AgentGraphState) -> Dict[str, Any]:
    """聚合器：将并行 Agent 的结果“压平”并生成统一摘要"""
    project: ProjectState = state["project_state"]
    active_node = project.get_active_node()
    next_step = project.next_step or {}
    
    parallel_agents = next_step.get("parallel_agents", [])
    if isinstance(parallel_agents, str): parallel_agents = [parallel_agents]
    if not parallel_agents and next_step.get("agent_name"):
        parallel_agents = [next_step.get("agent_name")]
    
    print(f"🏁 [Aggregator] Summarizing outputs from: {parallel_agents}")
    
    ensemble_summary = []
    
    for agent_name in parallel_agents:
        agent_role = agent_name.replace("_crew", "").capitalize()
        # 这里可以加入更多逻辑，读取子图的具体产出
        ensemble_summary.append(f"[{agent_role}]: Task Completed.") 
        
        if agent_name == "coding_crew" and project.code_blocks:
             ensemble_summary[-1] += f" (Code Generated)"
            
    final_digest = " | ".join(ensemble_summary)
    
    if active_node:
        active_node.semantic_summary = f"Execution Result: {final_digest}"
    
    # 清理 Next Step 状态，防止死循环
    project.next_step = None
    
    return {"project_state": project}

# --- Routing Logic ---

def route_next_step(state: AgentGraphState) -> Any:
    project = state["project_state"]
    decision = project.router_decision
    
    if decision == "finish": return "end"
    if decision == "human": return "orchestrator" 
    
    next_step = project.next_step
    if not next_step: return "orchestrator"
    
    # 支持并行路由
    parallel_agents = next_step.get("parallel_agents")
    if isinstance(parallel_agents, list) and parallel_agents:
        valid_routes = [a for a in parallel_agents if a in ["researcher", "coding_crew", "data_crew", "content_crew"]]
        if valid_routes:
            return valid_routes
            
    # 单一目标
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
    
    workflow = StateGraph(AgentGraphState)
    
    orch_prompt = load_prompt_file("agents/orchestrator/prompts/orchestrator.md")
    res_prompt = "Role: Research Assistant. Summarize search results into JSON."
    
    orchestrator = OrchestratorAgent(rotator, orch_prompt)
    researcher = ResearcherAgent(rotator, memory_tool, search_tool, res_prompt)
    
    # [关键] 传入 checkpointer 以支持子图持久化
    coding_app = build_coding_crew_graph(rotator, checkpointer)
    
    # --- Orchestrator Wrapper ---
    async def orchestrator_node(state: AgentGraphState):
        result = orchestrator.run(state)
        # Speculative execution logic can stay here...
        return result

    # --- Worker Wrappers ---
    async def call_coding(state: AgentGraphState):
        project = state["project_state"]
        
        # [New] 获取唯一的 Run ID
        run_id = project.next_step.get("run_id") or f"coding_default_{int(asyncio.get_event_loop().time())}"
        print(f"🔄 [Coding Crew] Starting Sub-graph Run ID: {run_id}")
        
        # 使用独立的 thread_id 运行子图，实现隔离与“翻篇”
        # 注意：这里我们使用 ainvoke，并传入 config
        res = await coding_app.ainvoke(
            common_input_mapper(state),
            config={"configurable": {"thread_id": run_id}}
        )
        
        code = res.get("generated_code", "")
        images = res.get("image_artifacts", [])
        
        if code: project.code_blocks["coding_crew"] = code
        if images: project.artifacts["images"] = images
        
        project.vector_clock["coding_crew"] = project.vector_clock.get("coding_crew", 0) + 1
        return {"project_state": project}

    async def call_data(state: AgentGraphState):
        # 类似 call_coding，可以扩展 Run ID 逻辑
        project = state["project_state"]
        project.vector_clock["data_crew"] = project.vector_clock.get("data_crew", 0) + 1
        return {"project_state": project} 

    async def call_content(state: AgentGraphState):
        project = state["project_state"]
        project.vector_clock["content_crew"] = project.vector_clock.get("content_crew", 0) + 1
        return {"project_state": project}

    # --- Nodes Definition ---
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("researcher", researcher.run) 
    workflow.add_node("coding_crew", call_coding)
    workflow.add_node("data_crew", call_data)
    workflow.add_node("content_crew", call_content)
    workflow.add_node("sync_gate", sync_gate_node)
    workflow.add_node("aggregator", call_aggregator)
    
    # --- Edges ---
    workflow.set_entry_point("orchestrator")
    
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
    
    worker_nodes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    for node in worker_nodes:
        workflow.add_edge(node, "sync_gate")
        
    workflow.add_edge("sync_gate", "aggregator")
    workflow.add_edge("aggregator", "orchestrator")
    
    return workflow.compile(checkpointer=checkpointer)
