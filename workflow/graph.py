import os
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END

# 核心依赖
# [Note] 这里的 Rotator 实际上充当了 LLM Client
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# Agent 定义
from agents.agents import ResearcherAgent, AgentGraphState
from agents.orchestrator.orchestrator import OrchestratorAgent

# 子图构建器
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
    print(f"⚠️ Warning: Prompt file not found at {path}")
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
    # [Updated] 从 next_step 获取当前单步指令
    instruction = "No instruction"
    if project.next_step and "instruction" in project.next_step:
        instruction = project.next_step["instruction"]
    
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
    
    return {"project_state": project}

def data_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    """处理 Data Crew 的输出"""
    project = state["project_state"]
    report = output.get("final_report") or output.get("analysis_draft", "")
    
    project.final_report = report
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Data Crew Output]\n{report}"}]})
    
    return {"project_state": project}

def content_output_mapper(state: AgentGraphState, output: Dict[str, Any]) -> Dict[str, Any]:
    """处理 Content Crew 的输出"""
    project = state["project_state"]
    content = output.get("final_content") or output.get("content_draft", "")
    
    project.final_report = content
    project.full_chat_history.append({"role": "model", "parts": [{"text": f"[Content Crew Output]\n{content}"}]})
    
    return {"project_state": project}


# =======================================================
# 2. 路由逻辑 (Refactored)
# =======================================================

def route_next_step(state: AgentGraphState) -> str:
    """
    基于 Supervisor 决策的动态路由。
    """
    current_state = state["project_state"]
    
    # 1. 优先检查 Router 决策
    decision = current_state.router_decision
    
    if decision == "finish":
        print("🏁 Project Completed. Routing to END.")
        return "end"
    
    if decision == "human":
        print("🚦 Routing to Orchestrator (Human Intervention Needed)")
        return "orchestrator"
        
    # 2. 获取目标 Agent (从 next_step 读取)
    next_step = current_state.next_step
    if not next_step:
        print("⚠️ No next_step found despite 'continue'. Routing back to Orchestrator.")
        current_state.user_feedback_queue = "System Error: Missing next_step configuration."
        return "orchestrator"
        
    next_agent = next_step.get("agent_name", "").lower()
    
    # 3. 验证并路由
    valid_routes = ["researcher", "coding_crew", "data_crew", "content_crew"]
    
    if next_agent in valid_routes: 
        print(f"👉 Routing to: {next_agent}")
        return next_agent
    
    # 4. 未知 Agent 处理
    print(f"⚠️ Unknown agent '{next_agent}'. Routing back to Orchestrator.")
    current_state.user_feedback_queue = f"Unknown agent in plan: {next_agent}"
    return "orchestrator"


# =======================================================
# 3. 构建主图
# =======================================================

def build_agent_workflow(
    rotator: GeminiKeyRotator, 
    memory_tool: VectorMemoryTool, 
    search_tool: GoogleSearchTool,
    checkpointer: Optional[Any] = None 
) -> StateGraph:
    
    # 1. 初始化 Prompt
    orch_prompt = load_prompt_file("agents/orchestrator/prompts/orchestrator.md")
    res_prompt = load_prompt_file("prompts/researcher_prompt.md")
    
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
    
    # 5. 注册子图节点
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
    
    # 闭环：所有工作节点完成后，必须回到 Orchestrator 进行下一轮决策
    for node in ["researcher", "coding_crew", "data_crew", "content_crew"]:
        workflow.add_edge(node, "orchestrator")
    
    # [Updated] 编译时传入 checkpointer 和中断点配置
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["coding_crew", "data_crew"]
    )
