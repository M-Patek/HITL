import json
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from core.utils import load_prompt
from config.keys import GEMINI_MODEL_NAME
from agents.crews.coding_crew.state import CodingCrewState
from tools.sandbox import DockerSandbox

# 全局沙箱
_sandbox = DockerSandbox()

class CodingCrewNodes:
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/coding_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def coder_node(self, state: CodingCrewState) -> Dict[str, Any]:
        iteration = state.get('iteration_count', 0) + 1
        print(f"\n👨‍💻 [Coder] 正在编写代码... (迭代: {iteration})")
        
        prompt_template = load_prompt(self.base_prompt_path, "coder.md")
        
        instruction = state.get("current_instruction", "")
        base_feedback = state.get("review_feedback", "")
        
        # 拼接报错信息
        exec_error = state.get("execution_stderr", "")
        if exec_error:
             base_feedback += f"\n\n⚠️ [RUNTIME ERROR]:\n{exec_error}\nFix it."

        # [New] 拼接图片生成成功的信息 (激励机制)
        images = state.get("image_artifacts", [])
        if images:
             img_names = ", ".join([i['filename'] for i in images])
             base_feedback += f"\n\n✅ [SUCCESS]: Previous code generated images: {img_names}. Good job."

        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            instruction=instruction,
            feedback=base_feedback if base_feedback else "无 (初始版本)"
        )

        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个资深 Python 工程师。只输出 Markdown 代码块。",
        )

        current_code = response.replace("```python", "").replace("```", "").strip() if response else ""
        
        return {
            "generated_code": current_code,
            "iteration_count": iteration
        }

    def executor_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """视觉增强型执行节点"""
        print(f"⚡️ [Executor] 正在沙箱中运行...")
        code = state.get("generated_code", "")
        
        if not code:
            return {"execution_passed": False, "execution_stderr": "No code"}

        # [Updated] 接收三个返回值
        stdout, stderr, images = _sandbox.run_code(code)
        
        is_success = not stderr
        if is_success:
            print(f"   ✅ 运行成功。Stdout: {stdout[:100]}...")
            if images:
                print(f"   📊 捕获到 {len(images)} 张图片产物！")
        else:
            print(f"   ❌ 运行时错误: {stderr[:100]}...")

        return {
            "execution_stdout": stdout,
            "execution_stderr": stderr,
            "execution_passed": is_success,
            "image_artifacts": images # 保存图片
        }

    def reviewer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        if not state.get("execution_passed", False):
            return {
                "review_status": "reject",
                "review_feedback": f"Runtime Error: {state.get('execution_stderr')}"
            }

        # [Optimized] 如果生成了图片，Reviewer 应该不仅看代码，还要看图片
        # 这是一个进阶优化：将图片 Base64 喂给 Gemini Vision 进行视觉审查
        # 这里暂时只做简单的文本审查
        
        print(f"🧐 [Reviewer] 代码运行通过，开始审查...")
        prompt = load_prompt(self.base_prompt_path, "reviewer.md").format(code=state.get("generated_code", ""))
        
        # 简单模拟审查通过，如果代码能跑且没明显问题
        # 在生产环境中，这里应调用 LLM
        return {"review_status": "approve", "review_feedback": "LGTM"}
