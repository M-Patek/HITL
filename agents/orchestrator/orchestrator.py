from typing import Dict, Any, Literal, TypedDict, Union
from pydantic import BaseModel
# 仅导入需要的类型，避免循环引用
from core.rotator import GeminiKeyRotator
from core.models import ProjectState

class SupervisorDecision(BaseModel):
    """定义 Supervisor 的单步决策结构"""
    next_agent: Literal["researcher", "coding_crew", "data_crew", "content_crew", "FINISH"]
    instruction: str
    reasoning: str

# Local definition to avoid circular imports
class LocalAgentGraphState(TypedDict):
    project_state: ProjectState

class OrchestratorAgent:
    """
    负责任务分解、动态规划和错误处理的核心大脑。
    已重构为 Supervisor Agent (单步决策模式)。
    """
    def __init__(self, rotator: GeminiKeyRotator, system_instruction: str):
        self.rotator = rotator
        self.system_instruction = system_instruction
        self.model = "gemini-2.5-flash" 
        
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # 兼容 LangGraph 的 State 传递
        current_state = state.get("project_state")
        if not current_state:
             print("⚠️ [Orchestrator] Warning: No project_state found in input.")
             return {}

        print(f"\n⚙️ [Orchestrator] 正在分析项目状态 (Supervisor Mode)...")
        
        # 1. 构建上下文
        context_str = f"Task: {current_state.user_input}\n"
        
        # 优先处理用户反馈
        if current_state.user_feedback_queue:
            print(f"🔔 [Orchestrator] 检测到用户干预/反馈: {current_state.user_feedback_queue}")
            context_str += f"USER INTERVENTION / FEEDBACK: {current_state.user_feedback_queue}\n"
            context_str += "Please replan based on this feedback immediately.\n"

        if current_state.last_error:
            context_str += f"Last Error: {current_state.last_error}\n"
            
        # 提取结构化 Artifacts 摘要
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
        
        # 提取历史
        history_summary = []
        if current_state.full_chat_history:
            for h in current_state.full_chat_history[-5:]: 
                 role = h.get('role', 'unknown')
                 parts = h.get('parts', [{'text': ''}])
                 text = parts[0].get('text', '') if parts else ''
                 history_summary.append(f"{role}: {text[:100]}...")

        # [Fix] 先将历史记录拼接成字符串，避免在 f-string 中使用反斜杠
        history_str = "\n".join(history_summary)

        prompt = f"""
        基于以下状态做出单步决策。
        
        注意：请优先检查 "Available Artifacts" 中的结构化数据，这比对话历史更准确。
        例如，如果 ResearchArtifact 已存在且包含足够信息，请勿再次调用 researcher。
        
        {context_str}
        {artifacts_str}
        
        当前对话历史片段 (History):
        {history_str}
        """

        try:
            # 2. 调用 LLM 获取单步计划
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

                # 4. 更新状态
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
