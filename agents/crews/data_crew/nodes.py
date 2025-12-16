import json
import os
from typing import Dict, Any
from core.rotator import GeminiKeyRotator
from agents.crews.data_crew.state import DataCrewState

class DataCrewNodes:
    """
    包含 Data Crew 内部所有节点的具体执行逻辑。
    """
    def __init__(self, rotator: GeminiKeyRotator, base_prompt_path: str = "agents/crews/data_crew/prompts"):
        self.rotator = rotator
        self.base_prompt_path = base_prompt_path

    def _load_prompt(self, filename: str) -> str:
        path = os.path.join(self.base_prompt_path, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def scientist_node(self, state: DataCrewState) -> Dict[str, Any]:
        """数据科学家节点：生成技术分析"""
        print(f"\n📊 [Data Scientist] 正在分析数据... (第 {state.get('iteration_count', 0) + 1} 次迭代)")
        
        prompt_template = self._load_prompt("scientist.md")
        feedback = state.get("business_feedback", "")
        
        # 尝试从历史记录中提取上下文，如果 raw_data_context 为空
        data_context = state.get("raw_data_context", "")
        if not data_context:
            # 简单的回退策略：使用最近的几次模型输出来充当上下文
            msgs = state.get("full_chat_history", [])[-3:]
            for msg in msgs:
                if msg.get("role") == "model":
                     parts = msg.get("parts", [{}])
                     if parts:
                        data_context += str(parts[0].get("text", ""))[:300] + "\n"
        
        if not data_context:
            data_context = "无可用外部数据，请基于常识或逻辑进行推演。"

        formatted_prompt = prompt_template.format(
            user_input=state.get("user_input", ""),
            instruction=state.get("current_instruction", ""),
            data_context=data_context,
            feedback=feedback if feedback else "无 (这是初稿)"
        )

        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个专注于数据洞察的科学家。请客观分析。"
        )

        # 简单的容错处理
        draft = response if response else "分析失败：无法生成内容。"

        return {
            "analysis_draft": draft,
            "iteration_count": state.get("iteration_count", 0) + 1
        }

    def analyst_node(self, state: DataCrewState) -> Dict[str, Any]:
        """商业分析师节点：审查价值"""
        print(f"💼 [Business Analyst] 正在评估商业价值...")
        
        prompt_template = self._load_prompt("analyst.md")
        report_to_review = state.get("analysis_draft", "")
        
        formatted_prompt = prompt_template.format(report=report_to_review)

        response = self.rotator.call_gemini_with_rotation(
            model_name="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": formatted_prompt}]}],
            system_instruction="你是一个严苛的商业分析师。只输出 JSON。",
            response_schema=None 
        )

        status = "reject"
        feedback = "解析失败"

        try:
            # 清理 Markdown 标记
            cleaned_response = response.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_response)
            
            status = result_json.get("status", "reject").lower()
            feedback = result_json.get("feedback", "")
            
            print(f"   📋 评估结果: {status.upper()} | 意见: {feedback[:50]}...")

        except Exception as e:
            print(f"   ❌ Analyst 解析错误: {e}")
            feedback = "JSON 解析错误，请重试。"

        return {
            "review_status": status,
            "business_feedback": feedback,
            # 如果通过，Draft 就直接晋升为 Final Report
            "final_report": report_to_review if status == "approve" else None 
        }
