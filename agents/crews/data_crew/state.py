from typing import TypedDict, Optional
from agents.common_types import BaseAgentState

class DataCrewState(BaseAgentState):
    """
    Data Crew 专属内部状态。
    负责在 Scientist 和 Analyst 之间流转数据和反馈。
    """
    current_instruction: str    # 具体的分析指令
    raw_data_context: str       # 能够访问到的数据上下文 (如 Research 结果)
    
    analysis_draft: str         # Scientist 的技术分析初稿
    business_feedback: str      # Analyst 的商业价值反馈
    review_status: str          # "approve" | "reject"
    iteration_count: int        # 迭代计数，用于防止无限循环
    
    final_report: str           # 最终通过审核的报告
