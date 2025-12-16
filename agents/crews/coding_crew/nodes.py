import json
import os
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from agents.crews.coding_crew.state import CodingCrewState

class CodingCrewNodes:
    """
    包含 Coding Crew 内部所有节点的具体执行逻辑。
    使用依赖注入的方式传入 Rotator。
    """
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/coding_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def _load_prompt(self, filename: str) -> str:
        path = os.path.join(self.base_prompt_path, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            return f"Error: Prompt file {filename} not found."

    def coder_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """Coder 节点：负责写代码或改代码"""
        print(f"\n👨‍💻 [Coder] 正在思考... (第 {state.get('iteration_count', 0) + 1} 次迭代)")
        
        prompt_template = self._load_prompt("coder.md")
        
        # 填充 Prompt
        instruction = state.get("current_instruction", "")
        feedback = state.get("review_feedback", "")
        user_input = state.get("user_input", "")
        
        formatted_prompt = prompt_template.format(
            user_input=user_input,
            instruction=instruction,
            feedback=feedback if feedback else "无 (这是第一版代码)"
        )

        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个只写代码的机器。只输出代码块。"
        )

        # 简单的后处理：提取代码块（这里简化处理，生产环境可以用正则更严谨地提取）
        code = response if response else "# Error generating code"
        
        return {
            "generated_code": code,
            "iteration_count": state.get("iteration_count", 0) + 1
        }

    def reviewer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """Reviewer 节点：负责审查"""
        print(f"🧐 [Reviewer] 正在审查代码...")
        
        prompt_template = self._load_prompt("reviewer.md")
        code_to_review = state.get("generated_code", "")
        
        formatted_prompt = prompt_template.format(code=code_to_review)

        # 强制要求 JSON 输出
        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个输出 JSON 的审查系统。",
            response_schema=None # 这里可以定义 Pydantic 模型来获得更严格的 JSON，为了简化代码暂时用文本解析
        )

        status = "reject"
        feedback = "解析审查结果失败"

        try:
            # 尝试解析 JSON (Gemini 有时会带 markdown code block)
            cleaned_response = response.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_response)
            status = result_json.get("status", "reject").lower()
            feedback = result_json.get("feedback", "")
            
            print(f"   📋 审查结果: {status.upper()} | 意见: {feedback[:50]}...")

        except Exception as e:
            print(f"   ❌ Reviewer 解析错误: {e}")
            feedback = f"JSON 解析错误，请重试。原始响应: {response}"

        return {
            "review_status": status,
            "review_feedback": feedback
        }
