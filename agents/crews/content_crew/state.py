from typing import TypedDict
from agents.common_types import BaseAgentState

class ContentCrewState(BaseAgentState):
    """
    Content Crew 专属内部状态。
    负责在 Writer 和 Editor 之间流转。
    """
    current_instruction: str    # 写作指令
    
    content_draft: str          # Writer 的初稿
    editor_feedback: str        # Editor 的修改意见
    
    review_status: str          # "approve" | "reject"
    iteration_count: int        # 迭代计数
    
    final_content: str          # 最终定稿
