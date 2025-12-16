from typing import Dict, Any, Literal, TypedDict, Union
from pydantic import BaseModel, Field
from core.rotator import GeminiKeyRotator
from core.models import ProjectState
from agents.common_types import BaseAgentState

class SupervisorDecision(BaseModel):
    """定义 Supervisor 的单步决策结构"""
    next_agent: Literal["researcher", "coding_crew", "data_crew", "content_crew", "FINISH"]
    instruction: str
    reasoning: str

class AgentGraphState(TypedDict):
    """(本地定义以支持类型提示) LangGraph 主图流转的状态"""
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
        
    def run(self, state: AgentGraphState) -> Dict[str, Any]:
        current_state = state["project_state"]
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
            
        # [Updated] 提取结构化 Artifacts 摘要
        artifacts_str = ""
        if current_state.artifacts:
            artifacts_str += "\nAvailable Artifacts (Structured Data):\n"
            for key, data in current_state.artifacts.items():
                if key == "research":
                    # 提取摘要和关键事实数量
                    summary = data.get("summary", "No summary")[:150]
                    fact_count = len(data.get("key_facts", []))
                    artifacts_str += f"- [ResearchArtifact]: {summary}... ({fact_count} key facts)\n"
                elif key == "code":
                    # 提取语言和文件数
                    lang = data.get("language", "Unknown")
                    file_count = len(data.get("files", {}))
                    artifacts_str += f"- [CodeArtifact]: {lang} project containing {file_count} files.\n"
                else:
                    artifacts_str += f"- [{key}]: Data available.\n"
        else:
            artifacts_str += "\nArtifacts: None yet.\n"
        
        # 提取最近的历史记录以辅助决策 (Context Awareness)
        history_summary = []
        for h in current_state.full_chat_history[-5:]: 
             role = h.get('role', 'unknown')
             text = h.get('parts', [{'text': ''}])[0].get('text', '')[:100]
             history_summary.append(f"{role}: {text}...")

        prompt = f"""
        基于以下状态做出单步决策。
        
        注意：请优先检查 "Available Artifacts" 中的结构化数据，这比对话历史更准确。
        例如，如果 ResearchArtifact 已存在且包含足够信息，请勿再次调用 researcher。
        
        {context_str}
        {artifacts_str}
        
        当前对话历史片段 (History):
        {"\n".join(history_summary)}
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
                # 3. 解析结果 (增强鲁棒性：同时支持 dict 和 json string)
                if isinstance(response, dict):
                    decision = SupervisorDecision.model_validate(response)
                else:
                    decision = SupervisorDecision.model_validate_json(response)
                    
                print(f"   🧠 决策: {decision.next_agent} | 原因: {decision.reasoning}")

                # 4. 更新状态 (Mapping to ProjectState fields)
                if decision.next_agent == "FINISH":
                    current_state.router_decision = "finish"
                    current_state.next_step = None
                    # 如果没有最终报告，将 instruction 作为总结
                    if not current_state.final_report:
                        current_state.final_report = decision.instruction
                else:
                    current_state.router_decision = "continue"
                    current_state.next_step = {
                        "agent_name": decision.next_agent, 
                        "instruction": decision.instruction
                    }
                
                # [Logic Check] 仅在成功规划后清除反馈
                current_state.user_feedback_queue = None
                current_state.last_error = None
                
            else:
                raise ValueError("Orchestrator API 返回为空")

        except Exception as e:
            print(f"❌ [Orchestrator] 规划失败: {e}")
            current_state.last_error = str(e)
            # 遇到严重错误，寻求人工介入
            current_state.router_decision = "human"
            # 注意：此处不清除 user_feedback_queue，保留给后续处理或人工查看

        return {"project_state": current_state}
