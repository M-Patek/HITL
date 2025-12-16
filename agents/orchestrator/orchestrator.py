from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from core.models import ProjectState, ExecutionPlan
from agents.common_types import BaseAgentState

# 注意：AgentGraphState 如果在 agents.py 中定义，为了避免循环引用，
# 我们可以只在这里引用需要的 ProjectState，因为 orchestrator 只需要操作 project_state
# 或者使用 TYPE_CHECKING
from typing import TypedDict

class AgentGraphState(TypedDict):
    """(本地定义以支持类型提示) LangGraph 主图流转的状态"""
    project_state: ProjectState

class OrchestratorAgent:
    """
    负责任务分解、动态规划和错误处理的核心大脑。
    已重构为独立模块。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash" 
        
    def run(self, state: AgentGraphState) -> Dict[str, Any]:
        current_state = state["project_state"]
        print(f"\n⚙️ [Orchestrator] 正在分析项目状态...")
        
        # 构建上下文
        context_str = f"Task: {current_state.user_input}\n"
        
        # 如果有用户反馈，这是最高优先级上下文
        if current_state.user_feedback_queue:
            print(f"🔔 [Orchestrator] 检测到用户干预/反馈: {current_state.user_feedback_queue}")
            context_str += f"USER INTERVENTION / FEEDBACK: {current_state.user_feedback_queue}\n"
            context_str += "Please replan based on this feedback immediately.\n"

        if current_state.research_summary:
            context_str += f"Research Summary: {current_state.research_summary[:200]}...\n"
        if current_state.last_error:
            context_str += f"Last Error: {current_state.last_error}\n"
        
        prompt = f"""
        基于以下状态生成 JSON 执行计划: 
        {context_str}
        
        当前已完成步骤 (History): {len(current_state.full_chat_history)} items.
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
                
                # 规划完成后，清除“已处理”的错误和反馈
                # 这样下次循环如果又有新错误，才会再次触发
                current_state.user_feedback_queue = None
                current_state.last_error = None
                
                print(f"✅ [Orchestrator] 计划已更新: 下一步执行 {len(plan_data.next_steps)} 个步骤。")
            else:
                raise ValueError("Orchestrator API 返回为空")

        except Exception as e:
            print(f"❌ [Orchestrator] 规划失败: {e}")
            current_state.last_error = str(e)
            # 严重错误时暂停计划
            current_state.execution_plan = []

        return {"project_state": current_state}
