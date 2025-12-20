import re
import json
import os
from typing import Dict, Any

from core.utils import load_prompt
from core.models import GeminiModel
from config.keys import GEMINI_MODEL_NAME
from agents.crews.coding_crew.state import CodingCrewState
from tools.sandbox import run_python_code

class CodingCrewNodes:
    def __init__(self, rotator):
        self.rotator = rotator
        # 获取当前文件所在目录的绝对路径，用于定位 prompts
        self.base_prompt_path = os.path.join(os.path.dirname(__file__), "prompts")

    def coder_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Coder] 负责编写代码。
        升级后：能听取 Reflector 的深度反思建议，而不仅仅是 Reviewer 的报错信息。
        """
        iteration = state.get("iteration_count", 0) + 1
        print(f"\n💻 [Coder] 正在编写代码... (第 {iteration} 次迭代)")
        
        prompt_template = load_prompt(self.base_prompt_path, "coder.md")
        
        # [🔥 Upgrade] 优先使用深度反思作为反馈
        reflection = state.get("reflection", "")
        raw_feedback = state.get("review_feedback", "")
        
        # 构造更强的反馈上下文
        if reflection:
            combined_feedback = f"### 🔧 Technical Lead's Fix Strategy (IMPORTANT):\n{reflection}\n\n### Original Review Issues:\n{raw_feedback}"
            print("   👀 Coder 已收到反思修复策略，正在应用...")
        else:
            combined_feedback = raw_feedback if raw_feedback else "None (First pass)"
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            instruction=state.get("current_instruction", ""),
            feedback=combined_feedback 
        )
        
        # 调用 Gemini 生成代码
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个 Python 专家。只输出 Markdown 代码块。",
            complexity="complex"
        )
        
        if not response:
            return {"generated_code": "", "iteration_count": iteration}

        # 提取代码
        code = response
        match = re.search(r"```python(.*?)```", response, re.DOTALL)
        if match:
            code = match.group(1).strip()
        else:
            match = re.search(r"```(.*?)```", response, re.DOTALL)
            if match:
                code = match.group(1).strip()
                
        # [🔥 Important] 每次重写后，清空上一轮的反思，避免干扰下一次（如果有的话）
        return {
            "generated_code": code,
            "iteration_count": iteration,
            "reflection": "" 
        }

    def executor_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Executor] 在沙箱中运行代码
        """
        print(f"🚀 [Executor] 正在执行代码...")
        code = state.get("generated_code", "")
        
        if not code:
            return {
                "execution_stdout": "", 
                "execution_stderr": "No code generated to execute.",
                "execution_passed": False
            }
            
        # 使用 sandbox 工具运行
        result = run_python_code(code)
        
        passed = (result["returncode"] == 0)
        status_icon = "✅" if passed else "❌"
        print(f"   {status_icon} 执行结束. Exit Code: {result['returncode']}")
        
        return {
            "execution_stdout": result["stdout"],
            "execution_stderr": result["stderr"],
            "execution_passed": passed,
            "image_artifacts": result.get("images", []) # 捕获生成的图片
        }

    def reviewer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Reviewer] 审查代码质量和执行结果
        """
        print(f"🧐 [Reviewer] 正在审查代码...")
        
        prompt_template = load_prompt(self.base_prompt_path, "reviewer.md")
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            code=state.get("generated_code", ""),
            stdout=state.get("execution_stdout", ""),
            stderr=state.get("execution_stderr", "")
        )
        
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个严格的代码审查员。以 JSON 格式输出。",
            complexity="complex"
        )
        
        # 解析 JSON 结果
        review_status = "reject"
        feedback = "Failed to parse review."
        report = {}
        
        try:
            # 尝试提取 JSON 块
            match = re.search(r"```json(.*?)```", response, re.DOTALL)
            json_str = match.group(1).strip() if match else response
            report = json.loads(json_str)
            
            review_status = report.get("status", "reject").lower()
            feedback = report.get("feedback", "")
            
        except Exception as e:
            print(f"   ❌ JSON 解析失败: {e}")
            feedback = f"Review parsing error: {response}"

        print(f"   📝 审查结果: {review_status.upper()}")
        
        return {
            "review_status": review_status,
            "review_feedback": feedback,
            "review_report": report
        }

    def reflector_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [🔥 New Node] Reflector (The Fixer)
        当代码失败时，分析根本原因并制定修复策略。
        """
        print(f"🔧 [Reflector] 正在进行深度归因分析...")
        
        prompt_template = load_prompt(self.base_prompt_path, "reflection.md")
        
        # 搜集所有错误证据，传给 Reflector 提示词
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            code=state.get("generated_code", ""),
            execution_stderr=state.get("execution_stderr", "None"),
            review_report=json.dumps(state.get("review_report", {}), indent=2)
        )
        
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个经验丰富的技术 Lead。请分析代码失败的原因并给出具体修复策略。",
            complexity="complex"
        )
        
        print(f"   💡 反思报告: 已生成")
        
        return {
            "reflection": response
        }

    def summarizer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Summarizer] 总结最终成果
        """
        print(f"📝 [Summarizer] 正在生成最终报告...")
        
        prompt_template = load_prompt(self.base_prompt_path, "summarizer.md")
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            code=state.get("generated_code", ""),
            execution_output=state.get("execution_stdout", "")
        )
        
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="总结任务完成情况。",
            complexity="simple"
        )
        
        return {
            "final_output": response
        }
