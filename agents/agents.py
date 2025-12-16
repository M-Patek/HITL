from typing import TypedDict
from core.rotator import GeminiKeyRotator
from core.models import ProjectState, ExecutionPlan
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

# LangGraph State 定义 (主图)
class AgentGraphState(TypedDict):
    project_state: ProjectState

# =======================================================
# 1. Orchestrator Agent (保持不变，负责总控)
# =======================================================

class OrchestratorAgent:
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash" 
        
    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        print(f"\n⚙️ [Orchestrator] 正在分析项目状态...")
        
        # ... (此处省略具体的 Prompt 构建逻辑，与之前类似，保持核心逻辑) ...
        # ... (为节省篇幅，重点展示架构变化) ...
        
        context_str = f"Task: {current_state.user_input}\n"
        if current_state.last_error:
             context_str += f"Last Error: {current_state.last_error}\n"
        
        # 简化版 Prompt
        prompt = f"""
        基于以下状态生成 JSON 执行计划: {context_str}
        可用 Agent: 'researcher', 'coding_crew' (Subgraph)
        """

        try:
            response_text = self.rotator.call_gemini_with_rotation(
                model_name=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=ExecutionPlan
            )
            
            if response_text:
                plan_data = ExecutionPlan.model_validate_json(response_text)
                current_state.execution_plan = [step.model_dump() for step in plan_data.next_steps]
                current_state.user_feedback_queue = None
                current_state.last_error = None
                print(f"✅ [Orchestrator] 计划已更新: {len(plan_data.next_steps)} 步")
            else:
                raise ValueError("API returned None")

        except Exception as e:
            print(f"❌ Orchestrator Error: {e}")
            current_state.last_error = str(e)

        return {"project_state": current_state}


# =======================================================
# 2. Researcher Agent (保持单节点，不需要复杂 Subgraph)
# =======================================================
class ResearcherAgent:
    def __init__(self, rotator: GeminiKeyRotator, memory_tool: VectorMemoryTool, search_tool: GoogleSearchTool, system_instruction: str):
        self.rotator = rotator
        self.memory_tool = memory_tool 
        self.search_tool = search_tool
        self.system_instruction = system_instruction

    def run(self, state: AgentGraphState) -> AgentGraphState:
        current_state = state["project_state"]
        if not current_state.execution_plan: return state
        
        instruction = current_state.execution_plan[0]['instruction']
        print(f"\n🔬 [Researcher] 开始搜索: {instruction[:30]}...")
        
        try:
            results = self.search_tool.search(instruction)
            # ... (调用 Gemini 总结) ...
            summary = f"基于搜索结果 '{results[:20]}...' 的总结。" # 模拟总结
            
            current_state.research_summary = summary
            current_state.execution_plan.pop(0) # 完成任务
            print("✅ Researcher 完成。")
            
        except Exception as e:
            current_state.last_error = f"Researcher Failed: {e}"
            current_state.user_feedback_queue = "Researcher failed, please replan."
            
        return {"project_state": current_state}

# 注意：SimulatedCrewAgent 已被彻底移除！现在我们用真正的 Subgraph。
