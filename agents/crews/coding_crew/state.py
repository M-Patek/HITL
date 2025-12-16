from typing import Literal
from agents.common_types import BaseAgentState

class CodingCrewState(BaseAgentState):
    """
    Coding Crew 内部专用状态。
    """
    current_instruction: str    # 当前指令
    generated_code: str         # Coder 生成的代码
    review_feedback: str        # Reviewer 的反馈
    review_status: str          # "approve" | "reject" | "pending"
    iteration_count: int        # 循环计数
    final_output: str           # 最终确认的代码
