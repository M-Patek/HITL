from typing import TypedDict, Optional, List, Dict
from agents.common_types import BaseAgentState

# =======================================================
# Coding Crew 专属的内部状态 (Private State)
# =======================================================

class CodingCrewState(BaseAgentState):
    """
    Coding Crew 子图的内部状态。
    这里的数据只在 Coder 和 Reviewer 之间流转，
    只有最终结果会合并回主图。
    """
    # 继承了 BaseAgentState，所以拥有 task_id 等基础信息
    
    current_instruction: str    # 当前的具体编程指令
    generated_code: str         # Coder 生成的代码
    review_feedback: str        # Reviewer 的反馈意见
    review_status: str          # "approve" | "reject" | "pending"
    iteration_count: int        # 循环次数，防止死循环
    final_output: str           # 最终确认的代码（准备输出给主图）
