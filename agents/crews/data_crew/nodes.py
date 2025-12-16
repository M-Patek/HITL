import json
import os
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from agents.crews.data_crew.state import DataCrewState

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
        
        formatted_prompt = prompt_template.format(report=report_to_review)

        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个严苛的商业分析师。只输出 JSON。",
            response_schema=None 
        )

        status = "reject"
        feedback = "Parsing failed"
        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            res = json.loads(cleaned)
            status = res.get("status", "reject").lower()
            feedback = res.get("feedback", "")
            print(f"   📋 评估结果: {status.upper()} | 意见: {feedback[:50]}...")
        except Exception: pass

        return {
            "review_status": status,
            "business_feedback": feedback,
            "final_report": report_to_review if status == "approve" else None 
        }
