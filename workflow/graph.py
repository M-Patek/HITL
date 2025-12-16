from typing import TypedDict
from langgraph.graph import StateGraph, END
import os 

from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
# 导入通用 Crew 类
from agents.agents import OrchestratorAgent, ResearcherAgent, SimulatedCrewAgent, AgentGraphState


def load_prompt_file(file_path: str) -> str:
    """从指定路径读取并返回 Prompt 文本。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"❌ 警告: 未找到 Prompt 文件 '{file_path}'。")
        return ""


def route_next_step(state: AgentGraphState) -> str:
    current_state = state["project_state"]
    
    if current_state.user_feedback_queue:
        print("🚨 发现用户反馈！流程中断，重定向到 Orchestrator 进行修正。")
        return "orchestrator"
    
    if not current_state.execution_plan:
        return "end" 
        
    next_step = current_state.execution_plan[0]
    next_agent_name = next_step.get('agent', '').lower()
    
    # [UPDATED] 允许的 Agent 列表更新为三大战队
    valid_agents = ["researcher", "orchestrator", "coding_crew", "data_crew", "content_crew"]
    
    if next_agent_name in valid_agents: 
        return next_agent_name
    else:
        print(f"❌ 计划中的 Agent '{next_agent_name}' 不存在，返回 Orchestrator 修正。")
        current_state.user_feedback_queue = f"计划中包含了未定义的 Agent '{next_agent_name}'，请修正计划。" 
        return "orchestrator"


def build_agent_workflow(rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool) -> StateGraph:
    
    base_prompt_path = "prompts" 
    
    # 1. 加载 Prompts
    orchestrator_instruction = load_prompt_file(os.path.join(base_prompt_path, "orchestrator_prompt.md"))
    researcher_instruction = load_prompt_file(os.path.join(base_prompt_path, "researcher_prompt.md"))
    
    # 加载战队 Prompts
    coding_crew_prompt = load_prompt_file(os.path.join(base_prompt_path, "coding_crew_prompt.md"))
    data_crew_prompt = load_prompt_file(os.path.join(base_prompt_path, "data_crew_prompt.md"))
    content_crew_prompt = load_prompt_file(os.path.join(base_prompt_path, "content_crew_prompt.md"))
    
    # 2. 初始化 Agent 实例
    orchestrator_agent_instance = OrchestratorAgent(rotator, orchestrator_instruction)
    researcher_agent_instance = ResearcherAgent(rotator, memory_tool, search_tool, researcher_instruction) 
    
    # [UPDATED] 实例化三大战队
    coding_crew_instance = SimulatedCrewAgent(rotator, coding_crew_prompt, crew_name="Coding Crew", output_target="code")
    data_crew_instance = SimulatedCrewAgent(rotator, data_crew_prompt, crew_name="Data Crew", output_target="report")
    content_crew_instance = SimulatedCrewAgent(rotator, content_crew_prompt, crew_name="Content Crew", output_target="report")
    
    # 3. 定义图
    workflow = StateGraph(AgentGraphState)
    
    # 4. 添加节点
    workflow.add_node("orchestrator", orchestrator_agent_instance.run)
    workflow.add_node("researcher", researcher_agent_instance.run)
    # 注册战队节点
    workflow.add_node("coding_crew", coding_crew_instance.run)
    workflow.add_node("data_crew", data_crew_instance.run)
    workflow.add_node("content_crew", content_crew_instance.run)
    
    # 5. 设置入口
    workflow.set_entry_point("orchestrator") 
    
    # 6. 定义边
    workflow.add_conditional_edges(
        "orchestrator", 
        route_next_step, 
        {
            "researcher": "researcher",
            "coding_crew": "coding_crew",
            "data_crew": "data_crew",
            "content_crew": "content_crew",
            "end": END,
            "orchestrator": "orchestrator"
        }
    )
    
    # 所有节点闭环回 Orchestrator
    workflow.add_edge("researcher", "orchestrator")
    workflow.add_edge("coding_crew", "orchestrator")
    workflow.add_edge("data_crew", "orchestrator")
    workflow.add_edge("content_crew", "orchestrator")
    
    app = workflow.compile()
    
    return app
