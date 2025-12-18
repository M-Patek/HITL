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

    # ... (coder_node 和 executor_node 保持不变，省略以节省空间) ...
    def coder_node(self, state: CodingCrewState) -> Dict[str, Any]:
        # (保持原有的 coder_node 逻辑)
        # 为方便合并，这里仅展示未修改部分的占位
        iteration = state.get('iteration_count', 0) + 1
        print(f"\n👨‍💻 [Coder] 正在编写代码... (迭代: {iteration})")
        prompt_template = load_prompt(self.base_prompt_path, "coder.md")
        instruction = state.get("current_instruction", "")
        base_feedback = state.get("review_feedback", "")
        reflection = state.get("reflection_analysis", "")
        if reflection: base_feedback += f"\n\n🔍 [LEAD REFLECTION]:\n{reflection}"
        exec_error = state.get("execution_stderr", "")
        if exec_error and "Runtime Error" not in base_feedback: base_feedback += f"\n\n⚠️ [RUNTIME ERROR]:\n{exec_error}"
        images = state.get("image_artifacts", [])
        if images: base_feedback += f"\n\n✅ [SUCCESS]: Generated images: {', '.join([i['filename'] for i in images])}."
        formatted_prompt = prompt_template.format(user_input=state.get("user_input", ""), instruction=instruction, feedback=base_feedback if base_feedback else "无")
        response = self.rotator.call_gemini_with_rotation(model_name=GEMINI_MODEL_NAME, contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}], system_instruction="Python Engineer. Markdown code only.")
        current_code = response.replace("```python", "").replace("```", "").strip() if response else ""
        return {"generated_code": current_code, "iteration_count": iteration, "reflection_analysis": None}

    def executor_node(self, state: CodingCrewState) -> Dict[str, Any]:
        # (保持原有的 executor_node 逻辑)
        print(f"⚡️ [Executor] 正在沙箱中运行...")
        code = state.get("generated_code", "")
        if not code: return {"execution_passed": False, "execution_stderr": "No code"}
        stdout, stderr, images = _sandbox.run_code(code)
        is_success = not stderr
        if is_success: print(f"   ✅ 运行成功。")
        else: print(f"   ❌ 运行时错误: {stderr[:100]}...")
        return {"execution_stdout": stdout, "execution_stderr": stderr, "execution_passed": is_success, "image_artifacts": images}

    def reviewer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        print(f"🧐 [Reviewer] 代码审查中 (Protocol & Vision Check)...")
        
        # [Update] 传入 user_input 以便进行视觉对齐检查
        prompt_text = load_prompt(self.base_prompt_path, "reviewer.md").format(
            user_input=state.get("user_input", "Unknown Task"),
            code=state.get("generated_code", "")
        )
        
        message_parts = [{"text": prompt_text}]
        images = state.get("image_artifacts", [])
        
        if images:
            print(f"   👁️ [Vision] 检测到 {len(images)} 张图片，正在进行视觉对齐审查...")
            for img in images:
                message_parts.append({
                    "inline_data": {
                        "mime_type": img.get("mime_type", "image/png"),
                        "data": img.get("data")
                    }
                })
                message_parts.append({"text": f"\n[Attachment] Image: {img.get('filename')}"})

        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME, 
            contents=[{"role": "user", "parts": message_parts}],
            system_instruction="你是一个严格的代码审查官。如果提供了图片，必须结合图片和用户需求进行审查。只输出 JSON。",
            response_schema=None
        )
        
        status = "reject"
        feedback = "Review parsing failed"
        report = {}
        
        try:
            if not response: raise ValueError("Empty response")
            cleaned_res = response.replace("```json", "").replace("```", "").strip()
            report = json.loads(cleaned_res)
            status = report.get("status", "reject").lower()
            feedback = report.get("feedback", "")
            
            # 打印可视化评分
            if "visual_match" in report:
                vm = report["visual_match"]
                print(f"   🎨 视觉评分: {vm.get('score')} | 评价: {vm.get('comment')}")

        except Exception as e:
            print(f"⚠️ Review JSON 解析失败: {e}")
            feedback = f"System Error: {str(e)}"
        
        if not state.get("execution_passed", False):
            status = "reject"
            feedback = f"Runtime Error: {state.get('execution_stderr')}\n{feedback}"

        reflection_content = None
        if status == "reject":
            print(f"   💡 [Reflector] 生成反思报告...")
            reflection_prompt = load_prompt(self.base_prompt_path, "reflection.md").format(
                user_input=state.get("user_input", ""),
                code=state.get("generated_code", ""),
                execution_stderr=state.get("execution_stderr", "None"),
                review_report=json.dumps(report, ensure_ascii=False, indent=2)
            )
            reflection_content = self.rotator.call_gemini_with_rotation(
                model_name=GEMINI_MODEL_NAME,
                contents=[{"role": "user", "parts": [{"text": reflection_prompt}]}],
                system_instruction="你是一名技术 Lead。"
            )

        return {
            "review_status": status,
            "review_feedback": feedback,
            "review_report": report,
            "reflection_analysis": reflection_content 
        }

    def summarizer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        # (保持原有的 summarizer_node 逻辑)
        print(f"📝 [Summarizer] 正在生成子树执行报告 (RAPTOR)...")
        prompt = load_prompt(self.base_prompt_path, "summarizer.md").format(
            user_input=state.get("user_input", ""),
            code_length=len(state.get("generated_code", "")),
            exec_passed=state.get("execution_passed", False),
            review_status=state.get("review_status", "unknown"),
            reflections=state.get("reflection_analysis") or "None"
        )
        summary = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction="Technical Reporter. Pure text summary only."
        )
        return {"final_output": summary or "Summary failed."}
