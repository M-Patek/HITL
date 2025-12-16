import os
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

from agents.agents import OrchestratorAgent, ResearcherAgent, AgentGraphState
# 导入所有 Crew Subgraphs
from agents.crews.coding_crew.graph import build_coding_crew_graph
from agents.crews.data_crew.graph import build_data_crew_graph
from agents.crews.content_crew.graph import build_content_crew_graph

def load_prompt_file(path: str) -> str:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: return f.read().strip()
    return ""

# =======================================================
# 1. 适配器 (Mappers)
#    负责将主图状态映射给子图，并将子图结果收回主图
# =======================================================

def common_input_mapper(state: AgentGraphState) -> Dict[str, Any]:
    """通用的输入映射逻辑"""
    project = state["project_state"]
    instruction = project.execution_plan[0]['instruction'] if project.execution_plan else "No instruction"
    return {
        "task_id": project.task_id,
        "user_input": project.user_input,
        "full_chat_history": project.full_chat_history,
        "current_instruction": instruction,
        "iteration_count": 0,
        "review_status": "pending",
        # Data Crew 特有
        "raw_data_context": project.research_summary if project.research_summary else ""
    }

def coding_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    project = state["project_state"]
    code = output.get("generated_code", "")
    project.code_blocks["coding_crew"] = code
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Coding Crew Output]\n{code}"}]})
    if project.execution_plan: project.execution_plan.pop(0)
    return {"project_state": project}

def data_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    project = state["project_state"]
    report = output.get("final_report", output.get("analysis_draft", "")) # Fallback to draft
    project.final_report = report # 更新最终报告字段
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Data Crew Output]\n{report}"}]})
    if project.execution_plan: project.execution_plan.pop(0)
    return {"project_state": project}

def content_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    project = state["project_state"]
    content = output.get("final_content", output.get("content_draft", ""))
    project.final_report = content # 更新最终报告字段
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Content Crew Output]\n{content}"}]})
    if project.execution_plan: project.execution_plan.pop(0)
    return {"project_state": project}

# =======================================================
# 2. 路由逻辑
# =======================================================

def route_next_step(state: AgentGraphState) -> str:
    current_state = state["project_state"]
    if current_state.user_feedback_queue: return "orchestrator"
    if not current_state.execution_plan: return "end"
        
    next_agent = current_state.execution_plan[0].get('agent', '').lower()
    valid_routes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    
    if next_agent in valid_routes: return next_agent
    
    current_state.user_feedback_queue = f"Unknown agent: {next_agent}"
    return "orchestrator"

# =======================================================
# 3. 构建主图
# =======================================================

def build_agent_workflow(rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool) -> StateGraph:
    
    # Init Agents
    orchestrator = OrchestratorAgent(rotator, load_prompt_file("prompts/orchestrator_prompt.md"))
    researcher = ResearcherAgent(rotator, memory_tool, search_tool, load_prompt_file("prompts/researcher_prompt.md"))
    
    # Init Subgraphs
    coding_app = build_coding_crew_graph(rotator)
    data_app = build_data_crew_graph(rotator)
    content_app = build_content_crew_graph(rotator)
    
    workflow = StateGraph(AgentGraphState)
    
    workflow.add_node("orchestrator", orchestrator.run)
    workflow.add_node("researcher", researcher.run)
    
    # Register Subgraph Nodes using Wrappers (Async)
    async def call_coding(state: AgentGraphState):
        res = await coding_app.ainvoke(common_input_mapper(state))
        return coding_output_mapper(state, res)
        
    async def call_data(state: AgentGraphState):
        res = await data_app.ainvoke(common_input_mapper(state))
        return data_output_mapper(state, res)

    async def call_content(state: AgentGraphState):
        res = await content_app.ainvoke(common_input_mapper(state))
        return content_output_mapper(state, res)

    workflow.add_node("coding_crew", call_coding)
    workflow.add_node("data_crew", call_data)
    workflow.add_node("content_crew", call_content)
    
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
    
    # Edges back to Orchestrator
    for node in ["researcher", "coding_crew", "data_crew", "content_crew"]:
        workflow.add_edge(node, "orchestrator")
        
    return workflow.compile()
