from agents.common_types import BaseAgentState

class DataCrewState(BaseAgentState):
    """Data Crew 内部专用状态"""
    current_instruction: str
    raw_data_context: str       
    analysis_draft: str         
    business_feedback: str      
    review_status: str          
    iteration_count: int        
    final_report: str
