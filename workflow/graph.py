from typing import TypedDict
from langgraph.graph import StateGraph, END

# 从其他模块导入依赖
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from agents.agents import OrchestratorAgent, ResearcherAgent, AnalystAgent, AgentGraphState


# =======================================================
# 1. 控制流：动态路由与循环决策
# =======================================================

def route_next_step(state: AgentGraphState) -> str:
    """
    根据 Orchestrator Agent 生成的执行计划或用户反馈，决定下一个执行的 Agent 节点。
    """
    current_state = state["project_state"]
    
    # 1. 检查是否有用户反馈（优先级最高，触发 Orchestrator 修正）
    if current_state.user_feedback_queue:
        print("🚨 发现用户反馈！流程中断，重定向到 Orchestrator 进行修正。")
        return "orchestrator"
    
    # 2. 检查是否有待执行计划
    if not current_state.execution_plan:
        return "end" # 如果计划列表为空，流程结束
        
    # 3. 获取下一个要执行的 Agent 名称
    next_step = current_state.execution_plan[0]
    next_agent_name = next_step['agent'].lower()
    
    # 4. 确保目标 Agent 存在于图中 (未来拓展时，这里需要添加 Coder, Reviewer 等)
    if next_agent_name in ["researcher", "analyst", "orchestrator"]: 
        return next_agent_name
    else:
        # 如果计划的 Agent 名称不合法，返回给调度器进行修正
        print(f"❌ 计划中的 Agent '{next_agent_name}' 不存在，返回 Orchestrator 修正。")
        current_state.user_feedback_queue = f"计划中包含了未定义的 Agent '{next_agent_name}'，请修正计划。" 
        return "orchestrator"


# =======================================================
# 2. LangGraph 流程构建 (最终动态版本)
# =======================================================

def build_agent_workflow(rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool) -> StateGraph:
    """
    构建 LangGraph 的 Agent 协作流程图。
    流程：(Orchestrator) -> (Agent_X) -> (Orchestrator) -> ... -> END
    """
    
    # 1. 初始化所有 Agent 实例
    
    # 调度器 (大脑)
    orchestrator_instruction = "你是一名项目规划和调度专家，请严格遵循 JSON 格式输出 ExecutionPlan。"
    orchestrator_agent_instance = OrchestratorAgent(rotator, orchestrator_instruction)
    
    # 专业 Agent (执行者)
    researcher_instruction = "你是一名专业的研究员，你的职责是根据指令收集事实、数据并存储到记忆库。"
    analyst_instruction = "你是一名资深分析师，你的职责是根据数据提供深入洞察。"
    
    # 将依赖注入 Agent 实例
    researcher_agent_instance = ResearcherAgent(rotator, memory_tool, search_tool, researcher_instruction) 
    analyst_agent_instance = AnalystAgent(rotator, analyst_instruction)
    
    # 2. 定义图和状态
    workflow = StateGraph(AgentGraphState)
    
    # 3. 添加节点
    workflow.add_node("orchestrator", orchestrator_agent_instance.run)
    workflow.add_node("researcher", researcher_agent_instance.run)
    workflow.add_node("analyst", analyst_agent_instance.run)
    
    # 4. 设置入口
    workflow.set_entry_point("orchestrator") # 流程从调度器开始
    
    # 5. 定义边 (核心逻辑)
    
    # 调度器完成后，总是交给路由函数 route_next_step
    workflow.add_conditional_edges(
        "orchestrator", 
        route_next_step, 
        {
            "researcher": "researcher",
            "analyst": "analyst",
            "end": END,
            "orchestrator": "orchestrator" # 自我修正/循环
        }
    )
    
    # 专业 Agent 完成后，都必须返回给调度器，让其生成下一步计划
    workflow.add_edge("researcher", "orchestrator")
    workflow.add_edge("analyst", "orchestrator")
    
    # 6. 编译图
    app = workflow.compile()
    
    return app
