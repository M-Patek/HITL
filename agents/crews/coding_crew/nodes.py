import re
import json
from typing import Dict, Any, Literal
from pydantic import BaseModel

from core.rotator import GeminiKeyRotator
from core.utils import load_prompt
from core.sig_ha import sig_ha
from config.keys import GEMINI_MODEL_NAME
from agents.crews.coding_crew.state import CodingCrewState
from tools.sandbox import DockerSandbox

# --- 辅助模型 ---

class ReviewDecision(BaseModel):
    security: Dict[str, Any]
    efficiency: Dict[str, Any]
    robustness: Dict[str, Any]
    visual_match: Dict[str, Any]
    status: Literal["approve", "reject"]
    feedback: str

# --- 节点类 ---

class CodingCrewNodes:
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/coding_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path
        self.sandbox = DockerSandbox() # 实例化沙箱

    def coder_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Coder] 负责编写代码
        """
        iteration = state.get("iteration_count", 0) + 1
        print(f"\n💻 [Coder] 正在编写代码... (第 {iteration} 次迭代)")
        
        # 1. 签名
        sig_ha.update_trace_in_state(state, "CodingAgent")
        
        # 2. 准备上下文
        prompt_template = load_prompt(self.base_prompt_path, "coder.md")
        feedback = state.get("review_feedback", "")
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            instruction=state.get("current_instruction", ""),
            feedback=feedback if feedback else "None (First pass)"
        )
        
        # 3. 生成代码
        response = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个 Python 专家。只输出 Markdown 代码块。",
            complexity="complex"
        )
        
        # 4. 提取代码块 (```python ... ```)
        code = response
        match = re.search(r"```python(.*?)```", response, re.DOTALL)
        if match:
            code = match.group(1).strip()
        else:
            # 尝试不带 python 的代码块
            match = re.search(r"```(.*?)```", response, re.DOTALL)
            if match:
                code = match.group(1).strip()
                
        return {
            "generated_code": code,
            "iteration_count": iteration
        }

    def executor_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Executor] 在 Docker 沙箱中运行代码
        """
        print(f"⚙️ [Executor] 沙箱运行中...")
        code = state.get("generated_code", "")
        
        if not code:
            return {"execution_stderr": "No code generated.", "execution_passed": False}
            
        # 预热沙箱
        self.sandbox.warm_up()
        
        # 运行
        stdout, stderr, images = self.sandbox.run_code(code)
        
        passed = True
        if stderr and "Error" in stderr:
            passed = False
            print(f"   ❌ 运行报错: {stderr[:50]}...")
        else:
            print(f"   ✅ 运行成功。")
            if images:
                print(f"   🖼️ 捕获到 {len(images)} 张图片。")

        return {
            "execution_stdout": stdout,
            "execution_stderr": stderr,
            "execution_passed": passed,
            "image_artifacts": images
        }

    def reviewer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Reviewer] 审查代码和运行结果
        """
        print(f"🧐 [Reviewer] 正在审查...")
        
        # 1. 签名
        sig_ha.update_trace_in_state(state, "ReviewerAgent")
        
        prompt_template = load_prompt(self.base_prompt_path, "reviewer.md")
        
        # 构造上下文
        code_snippet = state.get("generated_code", "")
        exec_err = state.get("execution_stderr", "")
        
        # 如果运行失败，自动 Reject
        if exec_err:
            return {
                "review_status": "reject",
                "review_feedback": f"Runtime Error occurred:\n{exec_err}\nPlease fix the code to handle this error."
            }
            
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            code=code_snippet
        )
        
        # 2. 调用 Reviewer
        try:
            response = self.rotator.call_gemini_with_rotation(
                model_name=GEMINI_MODEL_NAME,
                contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
                system_instruction="你是一个严格的代码审查员。只输出 JSON。",
                response_schema=ReviewDecision
            )
            
            if not response: raise ValueError("Empty review response")
            
            decision = ReviewDecision.model_validate_json(response.replace("```json", "").replace("```", "").strip())
            
            print(f"   📋 审查结果: {decision.status.upper()}")
            if decision.status == "reject":
                print(f"   💬 反馈: {decision.feedback[:50]}...")
            
            return {
                "review_status": decision.status,
                "review_feedback": decision.feedback,
                "review_report": decision.model_dump()
            }
            
        except Exception as e:
            print(f"   ⚠️ Reviewer 解析失败: {e}")
            # 降级处理
            return {
                "review_status": "approve", # 避免死循环，若 review 挂了暂且放行
                "review_feedback": "Reviewer system error, manual check advised."
            }

    def summarizer_node(self, state: CodingCrewState) -> Dict[str, Any]:
        """
        [Summarizer] 总结任务结果，更新全局状态
        """
        print(f"📝 [Summarizer] 生成汇报...")
        
        prompt_template = load_prompt(self.base_prompt_path, "summarizer.md")
        
        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            code_length=len(state.get("generated_code", "")),
            exec_passed=state.get("execution_passed", False),
            review_status=state.get("review_status", ""),
            reflections="None"
        )
        
        summary = self.rotator.call_gemini_with_rotation(
            model_name=GEMINI_MODEL_NAME,
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个技术负责人。"
        )
        
        return {
            "final_output": summary
        }
