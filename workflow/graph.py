import os
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# 导入 Agents
from agents.agents import OrchestratorAgent, ResearcherAgent, AgentGraphState
# 导入新的 Crew Subgraphs
from agents.crews.coding_crew.graph import build_coding_crew_graph

def load_prompt_file(path: str) -> str:
    """Helper to load prompts"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: return f.read().strip()
    return ""

# =======================================================
# 状态转换函数 (关键！)
# =======================================================
# 将主图状态转换为 Coding Crew 子图所需的状态
def coding_crew_input_mapper(state: AgentGraphState) -> Dict[str, Any]:
    project = state["project_state"]
    instruction = project.execution_plan[0]['instruction'] if project.execution_plan else "No instruction"
    return {
        "task_id": project.task_id,
        "user_input": project.user_input,
        "full_chat_history": project.full_chat_history,
        "current_instruction": instruction,
        "iteration_count": 0,
        "review_status": "pending"
    }

# 将 Coding Crew 子图的输出合并回主图状态
def coding_crew_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    # output 是 CodingCrewState
    project = state["project_state"]
    
    # 保存生成的代码
    generated_code = output.get("generated_code", "")
    project.code_blocks["coding_crew_v2"] = generated_code
    
    # 记录日志
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Coding Crew Output]:\n{generated_code}"}]})
    
    # 移除已完成的任务
    if project.execution_plan:
        project.execution_plan.pop(0)
        
    return {"project_state": project}


def route_next_step(state: AgentGraphState) -> str:
    """主图路由逻辑"""
    current_state = state["project_state"]
    
    if current_state.user_feedback_queue:
        return "orchestrator"
    
    if not current_state.execution_plan:
        return "end" 
        
    next_agent = current_state.execution_plan[0].get('agent', '').lower()
    
    valid_routes = ["researcher", "coding_crew"] # 这里可以扩展 data_crew, content_crew
    
    if next_agent in valid_routes:
        return next_agent
    
    # 默认回滚
    current_state.user_feedback_queue = f"Unknown agent: {next_agent}"
    return "orchestrator"


def build_agent_workflow(rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool) -> StateGraph:
    
    # 1. 准备基础 Prompt
    orchestrator_prompt = load_prompt_file("prompts/orchestrator_prompt.md")
    researcher_prompt = load_prompt_file("prompts/researcher_prompt.md")
    
    # 2. 初始化单点 Agent
    orchestrator = OrchestratorAgent(rotator, orchestrator_prompt)
    researcher = ResearcherAgent(rotator, memory_tool, search_tool, researcher_prompt)
    
    # 3. 构建子图 (Subgraphs)
    # 这是一个编译好的 StateGraph，可以直接当作节点使用
    coding_crew_app = build_coding_crew_graph(rotator)
    
    # 4. 构建主图
    workflow = StateGraph(AgentGraphState)
    
    workflow.add_node("orchestrator", orchestrator.run)
    workflow.add_node("researcher", researcher.run)
    
    # 添加 Coding Crew 节点
    # 使用 .add_node(name, subgraph) 
    # 注意：在最新的 LangGraph 中，可以通过 input/output 参数做状态映射，或者直接传入 compiled graph
    # 只要 State Schema 兼容。如果不兼容，需要用函数包裹。
    # 这里我们演示最稳健的方法：在 node 函数里调用 subgraph
    
    async def call_coding_crew(state: AgentGraphState):
        input_data = coding_crew_input_mapper(state)
        # 调用子图
        result = await coding_crew_app.ainvoke(input_data)
        # 映射回主图
        return coding_crew_output_mapper(state, result)

    workflow.add_node("coding_crew", call_coding_crew)

    # 5. 设置边
    workflow.set_entry_point("orchestrator")
    
    workflow.add_conditional_edges(
        "orchestrator",
        route_next_step,
        {
            "researcher": "researcher",
            "coding_crew": "coding_crew",
            "orchestrator": "orchestrator",
            "end": END
        }
    )
    
    workflow.add_edge("researcher", "orchestrator")
    workflow.add_edge("coding_crew", "orchestrator")
    
    return workflow.compile()
