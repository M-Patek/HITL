import json
import time
from typing import Dict, Any, List
from pydantic import ValidationError

from core.rotator import GeminiKeyRotator
from core.models import ProjectState, OrchestratorDecision
from core.sig_ha import sig_ha
from config.keys import GEMINI_MODEL_NAME

class OrchestratorAgent:
    def __init__(self, rotator: GeminiKeyRotator, prompt_template: str):
        self.rotator = rotator
        self.prompt_template = prompt_template

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrator 主逻辑：分析状态 -> 制定下一步计划
        """
        project_state: ProjectState = state["project_state"]
        
        # 1. 签名溯源
        sig_ha.update_trace_in_state(project_state, "Orchestrator")
        
        # 2. [Intervention Check] 检查是否有用户的高优先级干预
        if project_state.user_feedback_queue:
            print(f"🚨 [Orchestrator] 检测到用户干预: {project_state.user_feedback_queue}")
            # 强制清空当前计划，优先响应用户
            project_state.next_step = {
                "agent_name": "planner", # 这里可以根据逻辑跳到任何地方，或者直接给 Coding
                "instruction": f"User Intervention: {project_state.user_feedback_queue}. Re-plan immediately.",
                "run_id": f"intervention_{int(time.time())}"
            }
            # 清空队列
            project_state.user_feedback_queue = ""
            project_state.router_decision = "tool" # 确保不直接结束
            return {"project_state": project_state}

        # 3. 构造 Prompt
        # 获取最近的一些执行摘要
        active_node = project_state.get_active_node()
        last_summary = active_node.semantic_summary if active_node else "None"
        
        formatted_prompt = self.prompt_template.format(
            task_description=project_state.user_input,
            current_status=json.dumps(project_state.model_dump(include={'task_status', 'artifacts'}), default=str),
            last_action_summary=last_summary
        )

        # 4. 调用 Gemini
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[
                {"role": "user", "parts": [{"text": formatted_prompt}]}
            ],
            system_instruction="You are the Orchestrator. Output JSON only.",
            response_schema=OrchestratorDecision
        )

        # 5. 解析结果
        try:
            if not response:
                raise ValueError("Empty response from Orchestrator")
                
            cleaned = response.replace("```json", "").replace("```", "").strip()
            decision = OrchestratorDecision.model_validate_json(cleaned)
            
            # 更新状态
            project_state.router_decision = decision.decision
            project_state.thought_process = decision.thought_process
            
            if decision.next_step:
                # [New] 为子任务生成唯一的 Run ID，用于日志隔离
                run_id = f"{decision.next_step.agent_name}_{int(time.time())}"
                
                project_state.next_step = {
                    "agent_name": decision.next_step.agent_name,
                    "instruction": decision.next_step.instruction,
                    "parallel_agents": decision.next_step.parallel_agents,
                    "run_id": run_id # <--- 关键：每个任务都有唯一ID
                }
            else:
                project_state.next_step = None
                
            if decision.final_report:
                project_state.final_report = decision.final_report
                
        except (ValidationError, ValueError) as e:
            print(f"⚠️ Orchestrator Parsing Error: {e}")
            # Fallback
            project_state.router_decision = "finish"
            project_state.final_report = f"System Error: {str(e)}"

        return {"project_state": project_state}
