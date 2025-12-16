from agents.common_types import BaseAgentState

class ContentCrewState(BaseAgentState):
    """Content Crew 内部专用状态"""
    current_instruction: str
    content_draft: str          
    editor_feedback: str        
    review_status: str          
    iteration_count: int        
    final_content: str
