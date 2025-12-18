import os
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from core.models import TaskStatus, ProjectState
from agents.agents import ResearcherAgent, AgentGraphState
from agents.orchestrator.orchestrator import OrchestratorAgent
from agents.crews.coding_crew.graph import build_coding_crew_graph
from agents.crews.data_crew.graph import build_data_crew_graph
from agents.crews.content_crew.graph import build_content_crew_graph

def load_prompt_file(path: str) -> str:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: return f.read().strip()
    return ""

# --- Mappers (Adapters for TaskTree) ---

def common_input_mapper(state: AgentGraphState) -> Dict[str, Any]:
    """
    将主图的 TaskNode 状态映射到子图所需的扁平状态
    """
    project = state["project_state"]
    active_node = project.get_active_node()
    
    if not active_node:
        return {} # Should not happen
        
    return {
        "task_id": project.task_id,
        "user_input": project.root_node.instruction, # 全局目标
        "full_chat_history": active_node.local_history, # 子图只看当前节点的局部历史
        "current_instruction": active_node.instruction, # 当前节点的具体指令
        "iteration_count": 0,
        "review_status": "pending",
        "image_artifacts": [] 
    }

# --- Router ---

def route_next_step(state: AgentGraphState) -> str:
    project = state["project_state"]
    decision = project.router_decision
    
    if decision == "finish": return "end"
    if decision == "human": return "orchestrator" # Re-plan after human input
    if decision == "tool": return "orchestrator" # Re-plan after tool (ReAct Loop)
    
    # 这里处理 ReAct 的 Delegate Action
    next_step = project.next_step
    if not next_step: return "orchestrator"
    
    # 如果是 Delegate 操作，Orchestrator 会设置 agent_name
    agent_name = next_step.get("agent_name", "").lower()
    valid_routes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    
    if agent_name in valid_routes:
        return agent_name
        
    return "orchestrator"

# --- Workflow Builder ---

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
    # data_app = ... (Assuming similar updates will be done for data_crew)
    # content_app = ...
    
    workflow = StateGraph(AgentGraphState)
    
    # --- Nodes ---
    
    workflow.add_node("orchestrator", orchestrator.run)
    workflow.add_node("researcher", researcher.run) # Researcher 需要同步更新以适配 TaskNode
    
    # Wrapper for Coding Crew (With RAPTOR Logic)
    async def call_coding(state: AgentGraphState):
        print(f"🔄 [Subtree] Entering Coding Crew...")
        # 1. Invoke Subgraph
        res = await coding_app.ainvoke(common_input_mapper(state))
        
        # 2. Extract Results
        project = state["project_state"]
        active_node = project.get_active_node()
        
        code = res.get("generated_code", "")
        images = res.get("image_artifacts", [])
        summary = res.get("final_output", "No summary.")
        
        # 3. Update State (Artifacts)
        if code:
            project.code_blocks["coding_crew"] = code
        if images:
            project.artifacts["images"] = images
            
        # 4. [RAPTOR Trigger] Update TaskNode Summary
        if active_node:
            print(f"🔼 [RAPTOR] Updating Node Summary: {summary[:50]}...")
            active_node.semantic_summary = summary
            active_node.status = TaskStatus.COMPLETED
            
            # 将总结作为一条 System Message 存入局部历史
            active_node.local_history.append({
                "role": "system", 
                "parts": [{"text": f"Subtree Execution Completed. Summary: {summary}"}]
            })
            
        return {"project_state": project}

    # Placeholder wrappers for other crews (Needs similar RAPTOR logic later)
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
            "orchestrator": "orchestrator", # Loop back for tools
            "end": END
        }
    )
    
    # All agents return to Orchestrator to update the Tree state
    for node in ["researcher", "coding_crew", "data_crew", "content_crew"]:
        workflow.add_edge(node, "orchestrator")
    
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["coding_crew", "data_crew"])
