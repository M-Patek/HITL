from typing import TypedDict
from langgraph.graph import StateGraph, END
import os 

# 从其他模块导入依赖
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
# 导入新的 CodingCrewAgent
from agents.agents import OrchestratorAgent, ResearcherAgent, AnalystAgent, CodingCrewAgent, AgentGraphState

# ... (load_prompt_file 函数保持不变) ...

def route_next_step(state: AgentGraphState) -> str:
    """
    根据 Orchestrator Agent 生成的执行计划或用户反馈，决定下一个执行的 Agent 节点。
    """
    current_state = state["project_state"]
    
    if current_state.user_feedback_queue:
        print("🚨 发现用户反馈！流程中断，重定向到 Orchestrator 进行修正。")
        return "orchestrator"
    
    if not current_state.execution_plan:
        return "end" 
        
    next_step = current_state.execution_plan[0]
    next_agent_name = next_step.get('agent', '').lower()
    
    # 更新允许的 Agent 列表，加入 'coding_crew'
    valid_agents = ["researcher", "analyst", "orchestrator", "coding_crew"]
    
    if next_agent_name in valid_agents: 
        return next_agent_name
    else:
        print(f"❌ 计划中的 Agent '{next_agent_name}' 不存在，返回 Orchestrator 修正。")
        current_state.user_feedback_queue = f"计划中包含了未定义的 Agent '{next_agent_name}'，请修正计划。" 
        return "orchestrator"


def build_agent_workflow(rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool) -> StateGraph:
    """
    构建 LangGraph 的 Agent 协作流程图。
    """
    base_prompt_path = "prompts" 
    
    orchestrator_instruction = load_prompt_file(os.path.join(base_prompt_path, "orchestrator_prompt.md"))
    researcher_instruction = load_prompt_file(os.path.join(base_prompt_path, "researcher_prompt.md"))
    analyst_instruction = load_prompt_file(os.path.join(base_prompt_path, "analyst_prompt.md"))
    
    # 2. 初始化所有 Agent 实例
    orchestrator_agent_instance = OrchestratorAgent(rotator, orchestrator_instruction)
    researcher_agent_instance = ResearcherAgent(rotator, memory_tool, search_tool, researcher_instruction) 
    analyst_agent_instance = AnalystAgent(rotator, analyst_instruction)
    
    # 初始化 CodingCrewAgent (不需要 Prompt 文件，因为它内部管理 CrewAI)
    coding_crew_instance = CodingCrewAgent(rotator)
    
    # 3. 定义图和状态
    workflow = StateGraph(AgentGraphState)
    
    # 4. 添加节点
    workflow.add_node("orchestrator", orchestrator_agent_instance.run)
    workflow.add_node("researcher", researcher_agent_instance.run)
    workflow.add_node("analyst", analyst_agent_instance.run)
    # 添加 Coding Crew 节点
    workflow.add_node("coding_crew", coding_crew_instance.run)
    
    # 5. 设置入口
    workflow.set_entry_point("orchestrator") 
    
    # 6. 定义边
    workflow.add_conditional_edges(
        "orchestrator", 
        route_next_step, 
        {
            "researcher": "researcher",
            "analyst": "analyst",
            "coding_crew": "coding_crew", # 添加路由路径
            "end": END,
            "orchestrator": "orchestrator"
        }
    )
    
    # 所有专业 Agent 返回 Orchestrator
    workflow.add_edge("researcher", "orchestrator")
    workflow.add_edge("analyst", "orchestrator")
    workflow.add_edge("coding_crew", "orchestrator") # Crew 完成后也回报给大脑
    
    app = workflow.compile()
    
    return app
