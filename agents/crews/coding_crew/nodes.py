import json
import os
import ast
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from agents.crews.coding_crew.state import CodingCrewState

class CodingCrewNodes:
    """
    Coding Crew 节点逻辑集合。
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
            print(f"⚠️ Warning: Prompt file {path} not found.")
            return ""

    def coder_node(self, state: CodingCrewState) -> Dict[str, Any]:
        iteration = state.get('iteration_count', 0) + 1
        print(f"\n👨‍💻 [Coder] 正在编写代码... (迭代: {iteration})")
        
        prompt_template = self._load_prompt("coder.md")
        instruction = state.get("current_instruction", "")
        # 获取来自 Reviewer 的外部反馈
        base_feedback = state.get("review_feedback", "")
        user_input = state.get("user_input", "")
        
        # [New] 语法检查循环 (Self-Correction Loop)
        max_syntax_retries = 3
        current_code = ""
        syntax_feedback = "" # 用于累积内部语法错误
        
        for attempt in range(max_syntax_retries):
            # 组合外部反馈和内部语法反馈
            effective_feedback = base_feedback
            if syntax_feedback:
                effective_feedback += f"\n\n[System Syntax Check]:\n{syntax_feedback}"
            
            formatted_prompt = prompt_template.format(
                user_input=user_input,
                instruction=instruction,
                feedback=effective_feedback if effective_feedback else "无 (初始版本)"
            )

            # 调用 LLM
            response = self.rotator.call_gemini_with_rotation(
                model_name="gemini-2.5-flash",
                contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
                system_instruction="你是一个资深 Python 工程师。只输出 Markdown 代码块。"
            )

            current_code = response if response else "# Error: Code generation failed"
            
            # 清理 Markdown 标记以便 parse
            clean_code = current_code.replace("```python", "").replace("```", "").strip()
            
            # [New] 执行 AST 语法检查
            try:
                if clean_code:
                    ast.parse(clean_code)
                # 如果通过检查，直接跳出循环
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
        
        prompt_template = self._load_prompt("reviewer.md")
        code_to_review = state.get("generated_code", "")
        
        formatted_prompt = prompt_template.format(code=code_to_review)

        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个严格的代码审查员。只输出 JSON。",
            response_schema=None 
        )

        status = "reject"
        feedback = "Reviewer output parsing failed"

        try:
            # 清理可能存在的 Markdown 标记
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
