from typing import List, Dict
from agents.common_types import BaseAgentState

class CodingCrewState(BaseAgentState):
    """
    Coding Crew 内部专用状态 (Visual Enhanced).
    """
    current_instruction: str    
    generated_code: str         
    review_feedback: str        
    review_status: str          
    iteration_count: int        
    final_output: str           

    # Sandbox Outputs
    execution_stdout: str       
    execution_stderr: str       
    execution_passed: bool      
    
    # [New] 图片产物 [{"filename": "plot.png", "data": "base64...", "mime": "image/png"}]
    image_artifacts: List[Dict[str, str]]
