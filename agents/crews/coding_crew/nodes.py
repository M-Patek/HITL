import json
import ast
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from core.utils import load_prompt  # [New] 使用工具函数
from config.keys import GEMINI_MODEL_NAME # [New] 使用配置
from agents.crews.coding_crew.state import CodingCrewState

class CodingCrewNodes:
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/coding_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def coder_node(self, state: CodingCrewState) -> Dict[str, Any]:
        iteration = state.get('iteration_count', 0) + 1
        print(f"\n👨‍💻 [Coder] 正在编写代码... (迭代: {iteration})")
        
        # [Update] 使用通用加载器
        prompt_template = load_prompt(self.base_prompt_path, "coder.md")
        
        instruction = state.get("current_instruction", "")
        base_feedback = state.get("review_feedback", "")
        user_input = state.get("user_input", "")
        
        max_syntax_retries = 3
        current_code = ""
        syntax_feedback = ""
        
        for attempt in range(max_syntax_retries):
            effective_feedback = base_feedback
            if syntax_feedback:
                effective_feedback += f"\n\n[System Syntax Check]:\n{syntax_feedback}"
            
            formatted_prompt = prompt_template.format(
                user_input=user_input,
                instruction=instruction,
                feedback=effective_feedback if effective_feedback else "无 (初始版本)"
            )

            response = self.rotator.call_gemini_with_rotation(
                model_name=GEMINI_MODEL_NAME, # [Update]
                contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
                system_instruction="你是一个资深 Python 工程师。只输出 Markdown 代码块。"
            )

            current_code = response if response else "# Error: Code generation failed"
            clean_code = current_code.replace("```python", "").replace("```", "").strip()
            
            try:
                if clean_code:
                    ast.parse(clean_code)
                if attempt > 0:
                    print(f"   ✅ [Syntax Check] 语法修复成功 (Attempt {attempt+1})")
                break 
            except SyntaxError as e:
                error_msg = f"Line {e.lineno}: {e.msg}"
                print(f"   ⚠️ [Syntax Check] 发现语法错误: {error_msg} (Retrying {attempt+1}/{max_syntax_retries})...")
                syntax_feedback = f"Previous code had a SyntaxError: {error_msg}. Please fix it."
        
        return {
            "generated_code": current_code,
            "iteration_count": iteration
        }

    def reviewer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        print(f"🧐 [Reviewer] 正在审查代码...")
        
        prompt_template = load_prompt(self.base_prompt_path, "reviewer.md")
        code_to_review = state.get("generated_code", "")
        formatted_prompt = prompt_template.format(code=code_to_review)

        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME, # [Update]
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个严格的代码审查员。只输出 JSON。",
            response_schema=None 
        )

        status = "reject"
        feedback = "Reviewer output parsing failed"

        try:
            cleaned_response = response.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_response)
            status = result_json.get("status", "reject").lower()
            feedback = result_json.get("feedback", "")
            print(f"   📋 审查结果: {status.upper()} | 意见: {feedback[:50]}...")
        except Exception as e:
            print(f"   ❌ JSON 解析错误: {e}")

        return {
            "review_status": status,
            "review_feedback": feedback
        }
