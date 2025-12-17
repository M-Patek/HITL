import json
from typing import Dict, Any, Literal
from pydantic import BaseModel, ValidationError
from core.rotator import GeminiKeyRotator
from core.utils import load_prompt
from config.keys import GEMINI_MODEL_NAME
from agents.crews.data_crew.state import DataCrewState

class AnalystDecision(BaseModel):
    status: Literal["approve", "reject"]
    feedback: str

class DataCrewNodes:
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/data_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def scientist_node(self, state: DataCrewState) -> Dict[str, Any]:
        print(f"\n📊 [Data Scientist] 正在分析数据... (迭代: {state.get('iteration_count', 0) + 1})")
        
        prompt_template = load_prompt(self.base_prompt_path, "scientist.md")
        feedback = state.get("business_feedback", "")
        data_context = state.get("raw_data_context", "") or "无可用数据上下文"
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            instruction=state.get("current_instruction", ""),
            data_context=data_context,
            feedback=feedback if feedback else "无 (初稿)"
        )

        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个客观的数据科学家。"
        )

        return {
            "analysis_draft": response or "Analysis failed",
            "iteration_count": state.get("iteration_count", 0) + 1
        }

    def analyst_node(self, state: DataCrewState) -> Dict[str, Any]:
        print(f"💼 [Business Analyst] 正在评估商业价值...")
        
        prompt_template = load_prompt(self.base_prompt_path, "analyst.md")
        report_to_review = state.get("analysis_draft", "")
        
        max_retries = 3
        status = "reject"
        feedback = "Validation failed"
        
        for attempt in range(max_retries):
            formatted_prompt = prompt_template.format(report=report_to_review)

            response = self.rotator.call_gemini_with_rotation(
                model_name=GEMINI_MODEL_NAME,
                contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
                system_instruction="你是一个严苛的商业分析师。只输出 JSON。",
                response_schema=AnalystDecision 
            )

            try:
                if not response: raise ValueError("Empty response")
                cleaned = response.replace("```json", "").replace("```", "").strip()
                decision = AnalystDecision.model_validate_json(cleaned)
                status = decision.status.lower()
                feedback = decision.feedback
                print(f"   📋 评估结果: {status.upper()} | 意见: {feedback[:50]}...")
                break

            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                print(f"   ⚠️ [JSON Validation] 格式校验失败: {e} (Retrying {attempt+1}/{max_retries})...")
                continue

        return {
            "review_status": status,
            "business_feedback": feedback,
            "final_report": report_to_review if status == "approve" else None 
        }
