import os
import asyncio
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from core.models import TaskStatus, ProjectState
from agents.agents import ResearcherAgent, AgentGraphState
from agents.orchestrator.orchestrator import OrchestratorAgent
from agents.crews.coding_crew.graph import build_coding_crew_graph
from agents.crews.coding_crew.nodes import _sandbox as coding_sandbox

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

def route_next_step(state: AgentGraphState) -> str:
    project = state["project_state"]
    decision = project.router_decision
    
    if decision == "finish": return "end"
    if decision == "human": return "orchestrator" 
    if decision == "tool": return "orchestrator" 
    
    next_step = project.next_step
    if not next_step: return "orchestrator"
    
    agent_name = next_step.get("agent_name", "").lower()
    valid_routes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    
    if agent_name in valid_routes:
        return agent_name
        
    return "orchestrator"

def build_agent_workflow(
    rotator: GeminiKeyRotator, 
    memory_tool: VectorMemoryTool, 
    search_tool: GoogleSearchTool,
    checkpointer: Any = None 
) -> StateGraph:
    
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
            agent_name = next_step.get("agent_name")
            spec_queries = next_step.get("speculative_queries")
            
            if agent_name == "coding_crew":
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
    
    async def call_coding(state: AgentGraphState):
        print(f"🔄 [Subtree] Entering Coding Crew...")
        res = await coding_app.ainvoke(common_input_mapper(state))
        project = state["project_state"]
        active_node = project.get_active_node()
        code = res.get("generated_code", "")
        images = res.get("image_artifacts", [])
        summary = res.get("final_output", "No summary.")
        
        if code: project.code_blocks["coding_crew"] = code
        if images: project.artifacts["images"] = images
        
        if active_node:
            print(f"🔽 [RAPTOR] Subtree Completed. Pruning Level 0 History...")
            
            # 1. Update High-Level Summary
            active_node.semantic_summary = summary
            active_node.status = TaskStatus.COMPLETED
            
            # 2. [RAPTOR Compression] 
            # 暴力剪枝：清空局部历史，仅保留一条 System Message 作为“墓碑”
            # 这确保了当 Orchestrator 回看这个节点时，只消耗极少的 Token
            active_node.local_history = [{
                "role": "system", 
                "parts": [{"text": f"✅ [ARCHIVED] Subtree execution pruned. Final Summary: {summary}"}]
            }]
            
        return {"project_state": project}

    async def call_data(state: AgentGraphState):
        return {"project_state": state["project_state"]} 
    async def call_content(state: AgentGraphState):
        return {"project_state": state["project_state"]}

    workflow.add_node("coding_crew", call_coding)
    workflow.add_node("data_crew", call_data)
    workflow.add_node("content_crew", call_content)
    
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
    for node in ["researcher", "coding_crew", "data_crew", "content_crew"]:
        workflow.add_edge(node, "orchestrator")
    
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["coding_crew", "data_crew"])
