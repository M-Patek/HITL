from typing import List, Dict, Any, Optional
from agents.common_types import BaseAgentState

class CodingCrewState(BaseAgentState):
    """
    Coding Crew 内部专用状态
    继承自 BaseAgentState，确保 task_id 等基础字段存在。
    """
    # 当前指令
    current_instruction: str
    
    # 核心产出
    generated_code: str = ""
    filename: str = "main.py"
    
    # 执行结果 (Sandbox)
    execution_stdout: str = ""
    execution_stderr: str = ""
    execution_passed: bool = False
    
    # 审查结果
    review_feedback: str = ""
    review_status: str = "pending" # pending, approve, reject
    review_report: Optional[Dict[str, Any]] = None
    
    # 自我修正计数
    iteration_count: int = 0
    
    # 最终对外输出
    final_output: str = ""
    
    # 视觉产物
    image_artifacts: List[Dict[str, str]] = []
    
    # 引用全局状态的 artifacts (Read-only copy usually)
    global_artifacts: Dict[str, Any] = {}
