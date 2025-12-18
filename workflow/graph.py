import os
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from agents.agents import ResearcherAgent, AgentGraphState
from agents.orchestrator.orchestrator import OrchestratorAgent
# [New] 导入 Planner
from agents.planner.planner import PlannerAgent
from agents.crews.coding_crew.graph import build_coding_crew_graph
from agents.crews.data_crew.graph import build_data_crew_graph
from agents.crews.content_crew.graph import build_content_crew_graph

# ... 辅助函数 load_prompt_file 保持不变 ...
def load_prompt_file(path: str) -> str:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: return f.read().strip()
    return ""

# ... Mappers ...

def common_input_mapper(state: AgentGraphState) -> Dict[str, Any]:
    # ... 保持不变 ...
    project = state["project_state"]
    instruction = "No instruction"
    if project.next_step and "instruction" in project.next_step:
        instruction = project.next_step["instruction"]
    return {
        "task_id": project.task_id,
        "user_input": project.user_input,
        "full_chat_history": project.full_chat_history,
        "current_instruction": instruction,
        "iteration_count": 0,
        "review_status": "pending",
        "raw_data_context": project.research_summary if hasattr(project, 'research_summary') else "",
        # [New] 传递图片以供子图可能的多模态理解
        "image_artifacts": [] 
    }

def coding_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    """[Updated] 处理 Coding Crew 输出，包含图片"""
    project = state["project_state"]
    code = output.get("generated_code", "")
    images = output.get("image_artifacts", [])
    
    project.code_blocks["coding_crew"] = code
    
    # 构造历史记录
    msg_text = f"[Coding Crew Output]\nCode Length: {len(code)}\n"
    
    if images:
        msg_text += f"Generated {len(images)} images: {', '.join([i['filename'] for i in images])}"
        # 这里可以将图片 Base64 存入 artifacts，供前端展示
        project.artifacts["images"] = images
    
    project.full_chat_history.append({"role": "model", "parts": [{"text": msg_text}]})
    
    return {"project_state": project}

# ... route_next_step 保持不变 ...
def route_next_step(state: AgentGraphState) -> str:
    decision = state["project_state"].router_decision
    if decision == "finish": return "end"
    if decision == "human": return "orchestrator"
    
    next_step = state["project_state"].next_step
    if not next_step: return "orchestrator"
    
    next_agent = next_step.get("agent_name", "").lower()
    valid_routes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    
    return next_agent if next_agent in valid_routes else "orchestrator"

# [Updated] Build Workflow
def build_agent_workflow(
    rotator: GeminiKeyRotator, 
    memory_tool: VectorMemoryTool, 
    search_tool: GoogleSearchTool,
    checkpointer: Any = None 
) -> StateGraph:
    
    orch_prompt = load_prompt_file("agents/orchestrator/prompts/orchestrator.md")
    res_prompt = "Role: Senior Research Assistant. Summarize search results into JSON."
    
    orchestrator = OrchestratorAgent(rotator, orch_prompt)
    researcher = ResearcherAgent(rotator, memory_tool, search_tool, res_prompt)
    
    # [New] Planner 暂时作为 Orchestrator 的辅助工具，或者作为独立节点
    # 为了保持图的简洁，我们这里暂不将 Planner 设为强制节点，
    # 而是让 Orchestrator 具备 "Planning Mode"。
    # 如果要显式加入 Planner 节点，可以在 Entry Point 处增加。
    
    coding_app = build_coding_crew_graph(rotator)
    data_app = build_data_crew_graph(rotator)
    content_app = build_content_crew_graph(rotator)
    
    workflow = StateGraph(AgentGraphState)
    
    workflow.add_node("orchestrator", orchestrator.run)
    workflow.add_node("researcher", researcher.run)
    
    # Wrappers
    async def call_coding(state: AgentGraphState):
        res = await coding_app.ainvoke(common_input_mapper(state))
        return coding_output_mapper(state, res)
        
    async def call_data(state: AgentGraphState):
        # 简单的 Mapper
        res = await data_app.ainvoke(common_input_mapper(state))
        project = state["project_state"]
        report = res.get("final_report", "")
        project.final_report = report
        project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Data Output]\n{report}"}]})
        return {"project_state": project}

    async def call_content(state: AgentGraphState):
        res = await content_app.ainvoke(common_input_mapper(state))
        project = state["project_state"]
        content = res.get("final_content", "")
        project.final_report = content
        project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Content Output]\n{content}"}]})
        return {"project_state": project}

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
    
    for node in ["researcher", "coding_crew", "data_crew", "content_crew"]:
        workflow.add_edge(node, "orchestrator")
    
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["coding_crew", "data_crew"])
