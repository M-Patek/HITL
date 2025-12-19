from typing import Dict, Any, TypedDict, Literal
from pydantic import BaseModel, Field

from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from core.sig_ha import sig_ha
from core.utils import load_prompt
from config.keys import GEMINI_MODEL_NAME

# 定义 Orchestrator 的输出结构
class OrchestratorDecision(BaseModel):
    next_agent: Literal["researcher", "coding_crew", "data_crew", "content_crew", "FINISH"]
    instruction: str
    reasoning: str

# 定义图的状态类型
class AgentGraphState(TypedDict):
    project_state: ProjectState

class OrchestratorAgent:
    def __init__(self, rotator: GeminiKeyRotator):
        self.rotator = rotator
        self.system_instruction = load_prompt("agents/orchestrator/prompts", "orchestrator.md")

    def run(self, state: AgentGraphState) -> Dict[str, Any]:
        print(f"\n🧠 [Orchestrator] 分析任务状态...")
        
        current_state = state["project_state"]
        
        # 1. SIG-HA 签名：证明 Orchestrator 正在思考
        sig_ha.update_trace_in_state(current_state, "OrchestratorAgent")
        
        # 2. 准备上下文
        # 将 Artifacts 转换为文本摘要，供大脑参考
        artifacts_summary = ""
        if current_state.artifacts:
            artifacts_summary = "\nExisting Artifacts:\n"
            for k, v in current_state.artifacts.items():
                artifacts_summary += f"- {k}: {str(v)[:200]}...\n"
        
        user_input = current_state.user_input
        last_step_output = ""
        if current_state.full_chat_history:
            last_msg = current_state.full_chat_history[-1]
            last_step_output = f"Last Agent Output ({last_msg.get('role')}): {str(last_msg.get('parts'))[:300]}..."

        prompt = f"""
        Current Task: {user_input}
        
        History Context:
        {last_step_output}
        
        {artifacts_summary}
        
        User Feedback (High Priority): {current_state.user_feedback_queue or "None"}
        
        Decide the next step.
        """

        # 3. 调用 Gemini
        decision = None
        try:
            response_text = self.rotator.call_gemini_with_rotation(
                model_name=GEMINI_MODEL_NAME,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=OrchestratorDecision,
                complexity="complex" # 大脑总是需要强推理
            )
            
            if response_text:
                decision = OrchestratorDecision.model_validate_json(response_text)
                print(f"   👉 决策: {decision.next_agent} | 原因: {decision.reasoning}")
            else:
                print("   ⚠️ Orchestrator 返回为空，默认结束。")
                decision = OrchestratorDecision(next_agent="FINISH", instruction="Error in orchestration.", reasoning="Empty response")

        except Exception as e:
            print(f"   ❌ Orchestrator Error: {e}")
            decision = OrchestratorDecision(next_agent="FINISH", instruction=f"System Error: {e}", reasoning="Crash")

        # 4. 更新状态
        next_step_dict = None
        if decision.next_agent != "FINISH":
            next_step_dict = {
                "agent_name": decision.next_agent,
                "instruction": decision.instruction
            }
        else:
            current_state.final_report = decision.instruction

        current_state.next_step = next_step_dict
        current_state.plan = decision.reasoning
        
        # 清空处理过的反馈
        current_state.user_feedback_queue = None

        return {"project_state": current_state}
