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
        
        # --- [Phase 2 Update] 增强反馈循环 ---
        # 如果存在反思报告，将其拼接到反馈中，强制 Coder 阅读
        reflection = state.get("reflection_analysis", "")
        if reflection:
            base_feedback += f"\n\n🔍 [LEAD REFLECTION & FIX STRATEGY]:\n{reflection}"
        
        # 拼接运行报错 (保留原有逻辑作为兜底)
        exec_error = state.get("execution_stderr", "")
        if exec_error and "Runtime Error" not in base_feedback:
             base_feedback += f"\n\n⚠️ [RUNTIME ERROR]:\n{exec_error}"

        # 拼接图片生成成功的信息 (激励机制)
        images = state.get("image_artifacts", [])
        if images:
             img_names = ", ".join([i['filename'] for i in images])
             base_feedback += f"\n\n✅ [SUCCESS]: Previous code generated images: {img_names}."

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
        
        # 清除旧的反思，以免污染下一次
        return {
            "generated_code": current_code,
            "iteration_count": iteration,
            "reflection_analysis": None 
        }

    def executor_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """视觉增强型执行节点"""
        print(f"⚡️ [Executor] 正在沙箱中运行...")
        code = state.get("generated_code", "")
        
        if not code:
            return {"execution_passed": False, "execution_stderr": "No code"}

        # 接收三个返回值
        stdout, stderr, images = _sandbox.run_code(code)
        
        is_success = not stderr
        if is_success:
            print(f"   ✅ 运行成功。")
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
        """
        [Phase 1 & 2 & 3 Update] 多维审查 + 自动反思 + 视觉闭环
        """
        # 即使运行失败，也进入 Review 流程，以便生成更智能的反思
        print(f"🧐 [Reviewer] 代码审查中 (Protocol & Vision Check)...")
        
        # 1. 准备 Prompt 文本
        prompt_text = load_prompt(self.base_prompt_path, "reviewer.md").format(
            code=state.get("generated_code", "")
        )
        
        # 2. [Phase 3] 构建多模态 Payload
        message_parts = [{"text": prompt_text}]
        images = state.get("image_artifacts", [])
        
        if images:
            print(f"   👁️ [Vision] 检测到 {len(images)} 张图片产物，正在上传给审查官...")
            for img in images:
                message_parts.append({
                    "inline_data": {
                        "mime_type": img.get("mime_type", "image/png"),
                        "data": img.get("data")
                    }
                })
                message_parts.append({"text": f"\n[Attachment] Image file: {img.get('filename')}"})

        # 3. 调用多模态 LLM
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME, 
            contents=[{"role": "user", "parts": message_parts}],
            system_instruction="你是一个严格的代码审查官。如果提供了图片，必须结合图片进行审查。只输出 JSON。",
            response_schema=None
        )
        
        status = "reject"
        feedback = "Review parsing failed"
        report = {}
        
        try:
            if not response: raise ValueError("Empty response from Reviewer")
            cleaned_res = response.replace("```json", "").replace("```", "").strip()
            report = json.loads(cleaned_res)
            status = report.get("status", "reject").lower()
            feedback = report.get("feedback", "")
            
            # 打印详细评分
            scores = []
            for dim in ["security", "efficiency", "robustness", "visual_match"]:
                if dim in report:
                    val = report[dim]
                    if isinstance(val, dict):
                        scores.append(f"{dim.capitalize()}: {val.get('score')}")
            print(f"   📊 评分: {', '.join(scores)} | 结论: {status.upper()}")

        except Exception as e:
            print(f"⚠️ Review JSON 解析失败: {e}")
            feedback = f"System Error: {str(e)}"
        
        # 如果运行时本来就失败了，强制覆盖状态为 Reject，但保留 Reviewer 对代码逻辑的评价
        if not state.get("execution_passed", False):
            status = "reject"
            feedback = f"Runtime Error occurred: {state.get('execution_stderr')}\n{feedback}"

        # --- [Phase 2 Update] 反思逻辑 ---
        reflection_content = None
        
        if status == "reject":
            print(f"   💡 [Reflector] 检测到 Reject，正在生成反思报告...")
            reflection_prompt = load_prompt(self.base_prompt_path, "reflection.md").format(
                user_input=state.get("user_input", ""),
                code=state.get("generated_code", ""),
                execution_stderr=state.get("execution_stderr", "None"),
                review_report=json.dumps(report, ensure_ascii=False, indent=2)
            )
            
            reflection_content = self.rotator.call_gemini_with_rotation(
                model_name=GEMINI_MODEL_NAME,
                contents=[{"role": "user", "parts": [{"text": reflection_prompt}]}],
                system_instruction="你是一名技术 Lead，负责分析故障原因。"
            )
            if reflection_content:
                print(f"   📝 反思报告已生成 (长度: {len(reflection_content)})")

        return {
            "review_status": status,
            "review_feedback": feedback,
            "review_report": report,
            "reflection_analysis": reflection_content # 传递给 Coder
        }
