import json
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from core.utils import load_prompt
from config.keys import GEMINI_MODEL_NAME
from agents.crews.content_crew.state import ContentCrewState

class ContentCrewNodes:
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/content_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def writer_node(self, state: ContentCrewState) -> Dict[str, Any]:
        print(f"\n✍️ [Writer] 正在创作... (迭代: {state.get('iteration_count', 0) + 1})")
        
        prompt = load_prompt(self.base_prompt_path, "writer.md").format(
            user_input=state.get("user_input", ""),
            instruction=state.get("current_instruction", ""),
            feedback=state.get("editor_feedback", "") or "无 (初稿)"
        )

        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction="你是一个创意作家。"
        )
        
        return {
            "content_draft": response or "Content generation failed",
            "iteration_count": state.get("iteration_count", 0) + 1
        }

    def editor_node(self, state: ContentCrewState) -> Dict[str, Any]:
        print(f"🧐 [Editor] 正在审稿...")
        
        prompt = load_prompt(self.base_prompt_path, "editor.md").format(draft=state.get("content_draft", ""))
        
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction="你是一个挑剔的主编。只输出 JSON。",
            response_schema=None
        )

        status = "reject"
        feedback = "Parsing failed"
        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            res = json.loads(cleaned)
            status = res.get("status", "reject").lower()
            feedback = res.get("feedback", "")
            print(f"   📋 审稿结果: {status.upper()} | 意见: {feedback[:50]}...")
        except Exception: pass

        return {
            "review_status": status,
            "editor_feedback": feedback,
            "final_content": state.get("content_draft", "") if status == "approve" else None
        }
