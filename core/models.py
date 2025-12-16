import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError

# =======================================================
# 1. 共享内存结构：项目状态 (ProjectState)
# =======================================================

class ProjectState(BaseModel):
    """
    定义多 Agent 协作中的共享内存/项目状态。
    所有 Agent 的输入和输出都将通过这个结构进行。
    """
    task_id: str = Field(..., description="当前任务的唯一 ID。")
    user_input: str = Field(..., description="用户的原始任务描述。")
    
    # 核心产出数据
    research_summary: Optional[str] = Field(None, description="研究员 Agent 的最终结论摘要。")
    code_blocks: Dict[str, str] = Field(default_factory=dict, description="编码 Agent 生成的代码片段。")
    final_report: Optional[str] = Field(None, description="最终交付物。")
    
    # 协作与控制流
    execution_plan: List[Dict[str, str]] = Field(default_factory=list, description="调度器生成的动态执行计划（JSON）。")
    user_feedback_queue: Optional[str] = Field(None, description="用户实时介入的反馈，激活后流程中断。")
    
    # 历史记录 (维持记忆连续性)
    full_chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="所有 Agent 调用的完整输入/输出历史。")


# =======================================================
# 2. 调度器输出结构 (Execution Plan)
# =======================================================

class ExecutionStep(BaseModel):
    """定义调度器生成的单个执行步骤。"""
    agent: str = Field(..., description="要执行的 Agent 名称 (如: researcher, analyst, coder)。")
    instruction: str = Field(..., description="给该 Agent 的具体指令和焦点任务。")

class ExecutionPlan(BaseModel):
    """定义调度器生成的完整的执行计划。"""
    next_steps: List[ExecutionStep] = Field(..., description="按顺序执行的下一步任务列表。")
    is_complete: bool = Field(..., description="如果项目已完成，则设置为 True。")
