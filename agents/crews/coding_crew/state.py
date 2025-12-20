from typing import List, Dict, Any, Optional
from agents.common_types import BaseAgentState

class CodingCrewState(BaseAgentState):
    """
    Coding Crew 内部专用状态
    """
    # 继承自 BaseAgentState:
    # user_input: str
    # chat_history: List[BaseMessage]
    # next_step: str
    
    current_instruction: str
    generated_code: str = ""
    filename: str = "main.py"
    
    # 执行结果
    execution_stdout: str = ""
    execution_stderr: str = ""
    execution_passed: bool = False
    
    # Reviewer 反馈
    review_feedback: str = ""
    review_status: str = "pending" # 'approve', 'reject', 'pending'
    review_report: Optional[Dict[str, Any]] = None
    
    # [🔥 New] Tech Lead 的深度反思
    # 当 review_status 为 reject 时，由 Reflector 填充此字段，指导 Coder 进行修复
    reflection: str = "" 
    
    # 迭代控制
    iteration_count: int = 0
    final_output: str = ""
    
    # 产物
    image_artifacts: List[Dict[str, str]] = []
    global_artifacts: Dict[str, Any] = {}
