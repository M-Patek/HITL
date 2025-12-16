import json
import os
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from agents.crews.content_crew.state import ContentCrewState

class ContentCrewNodes:
    """
    包含 Content Crew 内部所有节点的具体执行逻辑。
    """
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/content_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def _load_prompt(self, filename: str) -> str:
        path = os.path.join(self.base_prompt_path, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def writer_node(self, state: ContentCrewState) -> Dict[str, Any]:
        """作家节点：进行创作"""
        print(f"\n✍️ [Creative Writer] 正在创作... (第 {state.get('iteration_count', 0) + 1} 次迭代)")
        
        prompt_template = self._load_prompt("writer.md")
        feedback = state.get("editor_feedback", "")
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            instruction=state.get("current_instruction", ""),
            feedback=feedback if feedback else "无 (这是初稿)"
        )

        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个创意作家，专注于高质量的内容生成。"
        )
        
        draft = response if response else "创作失败：无法生成内容。"
        
        return {
            "content_draft": draft,
            "iteration_count": state.get("iteration_count", 0) + 1
        }

    def editor_node(self, state: ContentCrewState) -> Dict[str, Any]:
        """主编节点：审稿"""
        print(f"🧐 [Chief Editor] 正在审稿...")
        
        prompt_template = self._load_prompt("editor.md")
        draft_to_review = state.get("content_draft", "")
        
        formatted_prompt = prompt_template.format(draft=draft_to_review)
        
        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个挑剔的主编。只输出 JSON。",
            response_schema=None
        )

        status = "reject"
        feedback = "解析失败"
        
        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            res_json = json.loads(cleaned)
            
            status = res_json.get("status", "reject").lower()
            feedback = res_json.get("feedback", "")
            
            print(f"   📋 审稿结果: {status.upper()} | 意见: {feedback[:50]}...")
            
        except Exception as e:
            print(f"   ❌ Editor 解析错误: {e}")
            feedback = "JSON 解析错误，请重试。"

        return {
            "review_status": status,
            "editor_feedback": feedback,
            "final_content": draft_to_review if status == "approve" else None
        }
