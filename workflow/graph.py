import os
from typing import Dict, Any
from langgraph.graph import StateGraph, END

# 核心依赖
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# Agent 定义
from agents.agents import OrchestratorAgent, ResearcherAgent, AgentGraphState

# 子图构建器 (Crew Subgraphs)
from agents.crews.coding_crew.graph import build_coding_crew_graph
from agents.crews.data_crew.graph import build_data_crew_graph
from agents.crews.content_crew.graph import build_content_crew_graph

# =======================================================
# 辅助函数
# =======================================================

def load_prompt_file(path: str) -> str:
    """安全加载 Prompt 文件内容"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: 
            return f.read().strip()
    return ""

# =======================================================
# 1. 适配器 (Mappers)
#    负责主图与子图之间的状态转换
# =======================================================

def common_input_mapper(state: AgentGraphState) -> Dict[str, Any]:
    """
    将主图状态映射为所有 Crew 都兼容的输入格式。
    """
    project = state["project_state"]
    instruction = project.execution_plan[0]['instruction'] if project.execution_plan else "No instruction"
    
    return {
        "task_id": project.task_id,
        "user_input": project.user_input,
        "full_chat_history": project.full_chat_history,
        "current_instruction": instruction,
        # 初始化子图控制变量
        "iteration_count": 0,
        "review_status": "pending",
        # 传递上下文数据
        "raw_data_context": project.research_summary if project.research_summary else ""
    }

def coding_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    """处理 Coding Crew 的输出"""
    project = state["project_state"]
    code = output.get("generated_code", "")
    
    project.code_blocks["coding_crew"] = code
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Coding Crew Output]\n{code}"}]})
    
    if project.execution_plan: 
        project.execution_plan.pop(0)
    return {"project_state": project}

def data_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    """处理 Data Crew 的输出"""
    project = state["project_state"]
    # 优先取 final_report，如果没有(比如被迫中断)，则取草稿
    report = output.get("final_report") or output.get("analysis_draft", "")
    
    project.final_report = report
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Data Crew Output]\n{report}"}]})
    
    if project.execution_plan: 
        project.execution_plan.pop(0)
    return {"project_state": project}

def content_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    """处理 Content Crew 的输出"""
    project = state["project_state"]
    content = output.get("final_content") or output.get("content_draft", "")
    
    project.final_report = content
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Content Crew Output]\n{content}"}]})
    
    if project.execution_plan: 
        project.execution_plan.pop(0)
    return {"project_state": project}


# =======================================================
# 2. 路由逻辑
# =======================================================

def route_next_step(state: AgentGraphState) -> str:
    current_state = state["project_state"]
    
    # 优先处理用户反馈
    if current_state.user_feedback_queue: 
        return "orchestrator"
    
    # 计划执行完毕
    if not current_state.execution_plan: 
        return "end"
        
    # 获取下一个 Agent 名称
    next_agent = current_state.execution_plan[0].get('agent', '').lower()
    
    # 合法的路由目标
    valid_routes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    
    if next_agent in valid_routes: 
        return next_agent
    
    # 未知 Agent，回退到调度器
    current_state.user_feedback_queue = f"Unknown agent in plan: {next_agent}"
    return "orchestrator"


# =======================================================
# 3. 构建主图
# =======================================================

def build_agent_workflow(rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool) -> StateGraph:
    
    # 1. 初始化通用 Prompt
    # 注意：确保 prompts 目录下存在这些文件
    orch_prompt = load_prompt_file("prompts/orchestrator_prompt.md")
    res_prompt = load_prompt_file("prompts/researcher_prompt.md") # 如果没有，请创建或使用默认值
    
    # 2. 初始化单点 Agent
    orchestrator = OrchestratorAgent(rotator, orch_prompt)
    researcher = ResearcherAgent(rotator, memory_tool, search_tool, res_prompt)
    
    # 3. 编译子图
    coding_app = build_coding_crew_graph(rotator)
    data_app = build_data_crew_graph(rotator)
    content_app = build_content_crew_graph(rotator)
    
    # 4. 构建主图结构
    workflow = StateGraph(AgentGraphState)
    
    workflow.add_node("orchestrator", orchestrator.run)
    workflow.add_node("researcher", researcher.run)
    
    # 5. 注册子图节点 (使用 Wrapper 函数处理异步调用和状态映射)
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
    
    # 6. 设置边和入口
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
    
    # 所有工作节点执行完后，都闭环回到 Orchestrator 进行检查或下一步规划
    for node in ["researcher", "coding_crew", "data_crew", "content_crew"]:
        workflow.add_edge(node, "orchestrator")
        
    return workflow.compile()
