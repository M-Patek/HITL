from typing import List, Dict, Any, Optional
from agents.common_types import BaseAgentState

class CodingCrewState(BaseAgentState):
    """
    Coding Crew 内部专用状态 (Visual Enhanced + Reflection).
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
    
    # [Visual Loop] 图片产物
    image_artifacts: List[Dict[str, str]]
    
    # [Protocol Phase 1] 结构化审查报告
    review_report: Optional[Dict[str, Any]] = None
    
    # [Protocol Phase 2] 反思与自愈报告
    reflection_analysis: Optional[str] = None
