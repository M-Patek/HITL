from typing import Dict, Any, Literal, TypedDict, Union
from pydantic import BaseModel
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from config.keys import GEMINI_MODEL_NAME

class SupervisorDecision(BaseModel):
    next_agent: Literal["researcher", "coding_crew", "data_crew", "content_crew", "FINISH"]
    instruction: str
    reasoning: str

class OrchestratorAgent:
    """
    负责任务分解、动态规划和错误处理的核心大脑。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        # [Update] 使用统一配置的模型
        self.model = GEMINI_MODEL_NAME
        # [Update] 历史记录窗口大小
        self.max_history_turns = 10
        
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        current_state = state.get("project_state")
        if not current_state:
             return {}

        print(f"\n⚙️ [Orchestrator] 正在分析项目状态 (Supervisor Mode)...")
        
        # 1. 构建上下文
        context_str = f"Task: {current_state.user_input}\n"
        
        if current_state.user_feedback_queue:
            print(f"🔔 [Orchestrator] 检测到用户干预/反馈: {current_state.user_feedback_queue}")
            context_str += f"USER INTERVENTION / FEEDBACK: {current_state.user_feedback_queue}\n"
            context_str += "Please replan based on this feedback immediately.\n"

        if current_state.last_error:
            context_str += f"Last Error: {current_state.last_error}\n"
            
        artifacts_str = ""
        if current_state.artifacts:
            artifacts_str += "\nAvailable Artifacts (Structured Data):\n"
            for key, data in current_state.artifacts.items():
                if key == "research":
                    summary = data.get("summary", "No summary")[:150]
                    fact_count = len(data.get("key_facts", []))
                    artifacts_str += f"- [ResearchArtifact]: {summary}... ({fact_count} key facts)\n"
                elif key == "code":
                    lang = data.get("language", "Unknown")
                    file_count = len(data.get("files", {}))
                    artifacts_str += f"- [CodeArtifact]: {lang} project containing {file_count} files.\n"
                else:
                    artifacts_str += f"- [{key}]: Data available.\n"
        else:
            artifacts_str += "\nArtifacts: None yet.\n"
        
        # [Update] 优化历史记录处理 (Context Window)
        history_summary = []
        full_history = current_state.full_chat_history
        # 只保留最近 N 条记录，避免 Token 溢出
        recent_history = full_history[-self.max_history_turns:] if full_history else []
        
        if recent_history:
            for h in recent_history: 
                 role = h.get('role', 'unknown')
                 parts = h.get('parts', [{'text': ''}])
                 text = parts[0].get('text', '') if parts else ''
                 # 进一步截断过长的单条消息
                 history_summary.append(f"{role}: {text[:200]}...")
        
        history_str = "\n".join(history_summary)

        prompt = f"""
        基于以下状态做出单步决策。
        
        {context_str}
        {artifacts_str}
        
        当前对话历史片段 (Last {len(recent_history)} turns):
        {history_str}
        """

        try:
            response = self.rotator.call_gemini_with_rotation(
                model_name=self.model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                system_instruction=self.system_instruction,
                response_schema=SupervisorDecision
            )
            
            if response:
                if isinstance(response, dict):
                    decision = SupervisorDecision.model_validate(response)
                else:
                    decision = SupervisorDecision.model_validate_json(response)
                    
                print(f"   🧠 决策: {decision.next_agent} | 原因: {decision.reasoning}")

                if decision.next_agent == "FINISH":
                    current_state.router_decision = "finish"
                    current_state.next_step = None
                    if not current_state.final_report:
                        current_state.final_report = decision.instruction
                else:
                    current_state.router_decision = "continue"
                    current_state.next_step = {
                        "agent_name": decision.next_agent, 
                        "instruction": decision.instruction
                    }
                
                current_state.user_feedback_queue = None
                current_state.last_error = None
                
            else:
                raise ValueError("Orchestrator API 返回为空")

        except Exception as e:
            print(f"❌ [Orchestrator] 规划失败: {e}")
            current_state.last_error = str(e)
            current_state.router_decision = "human"

        return {"project_state": current_state}
