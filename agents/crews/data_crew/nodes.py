import json
import os
from typing import Dict, Any, Literal
from pydantic import BaseModel, ValidationError
from core.rotator import GeminiKeyRotator
from agents.crews.data_crew.state import DataCrewState

# [New] 定义输出数据模型
class AnalystDecision(BaseModel):
    status: Literal["approve", "reject"]
    feedback: str

class DataCrewNodes:
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/data_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def _load_prompt(self, filename: str) -> str:
        path = os.path.join(self.base_prompt_path, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f: return f.read().strip()
        except FileNotFoundError: return ""

    def scientist_node(self, state: DataCrewState) -> Dict[str, Any]:
        print(f"\n📊 [Data Scientist] 正在分析数据... (迭代: {state.get('iteration_count', 0) + 1})")
        
        prompt_template = self._load_prompt("scientist.md")
        feedback = state.get("business_feedback", "")
        data_context = state.get("raw_data_context", "") or "无可用数据上下文"
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            instruction=state.get("current_instruction", ""),
            data_context=data_context,
            feedback=feedback if feedback else "无 (初稿)"
        )

        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个客观的数据科学家。"
        )

        return {
            "analysis_draft": response or "Analysis failed",
            "iteration_count": state.get("iteration_count", 0) + 1
        }

    def analyst_node(self, state: DataCrewState) -> Dict[str, Any]:
        print(f"💼 [Business Analyst] 正在评估商业价值...")
        
        prompt_template = self._load_prompt("analyst.md")
        report_to_review = state.get("analysis_draft", "")
        
        # [New] 自动重试与校验循环
        max_retries = 3
        status = "reject"
        feedback = "Validation failed"
        
        for attempt in range(max_retries):
            formatted_prompt = prompt_template.format(report=report_to_review)

            # 调用 LLM (尝试使用 response_schema 提示)
            response = self.rotator.call_gemini_with_rotation(
                model_name="gemini-2.5-flash",
                contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
                system_instruction="你是一个严苛的商业分析师。只输出 JSON。",
                response_schema=AnalystDecision 
            )

            try:
                if not response: raise ValueError("Empty response")

                # 1. 尝试清理 (处理可能存在的 Markdown 包裹)
                cleaned = response.replace("```json", "").replace("```", "").strip()
                
                # 2. Pydantic 严格校验
                decision = AnalystDecision.model_validate_json(cleaned)
                
                # 3. 提取有效数据
                status = decision.status.lower()
                feedback = decision.feedback
                print(f"   📋 评估结果: {status.upper()} | 意见: {feedback[:50]}...")
                
                # 校验成功，跳出重试
                break

            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                print(f"   ⚠️ [JSON Validation] 格式校验失败: {e} (Retrying {attempt+1}/{max_retries})...")
                # 继续下一次循环重试
                continue

        return {
            "review_status": status,
            "business_feedback": feedback,
            "final_report": report_to_review if status == "approve" else None 
        }
