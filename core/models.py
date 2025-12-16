from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# =======================================================
# 1. 共享内存结构：项目状态 (ProjectState)
# =======================================================

class ProjectState(BaseModel):
    """
    定义多 Agent 协作中的共享内存/项目状态。
    所有 Agent 的输入和输出都将通过这个结构进行。
    """
    # 基础信息
    task_id: str = Field(..., description="当前任务的唯一 ID")
    user_input: str = Field(..., description="用户的原始任务描述")
    
    # 产出数据 (Artifacts)
    research_summary: Optional[str] = Field(None, description="Researcher 的研究摘要")
    
    # [Updated] Coding Crew 产出
    code_blocks: Dict[str, str] = Field(default_factory=dict, description="Coding Crew 生成的代码 (Key=模块名)")
    
    # [Updated] Data & Content Crew 产出 (统一作为最终报告)
    final_report: Optional[str] = Field(None, description="最终交付物 (报告、文章或数据分析)")
    
    # 错误追踪与自愈
    last_error: Optional[str] = Field(None, description="最近一次发生的系统错误")
    user_feedback_queue: Optional[str] = Field(None, description="用户实时反馈，若存在则触发中断")
    
    # 流程控制
    execution_plan: List[Dict[str, str]] = Field(default_factory=list, description="Orchestrator 生成的执行计划")
    full_chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="完整对话历史")


# =======================================================
# 2. 调度器输出结构 (Execution Plan)
# =======================================================

class ExecutionStep(BaseModel):
    """定义单步执行动作"""
    agent: str = Field(..., description="目标 Agent (researcher, coding_crew, etc.)")
    instruction: str = Field(..., description="具体指令")

class ExecutionPlan(BaseModel):
    """Orchestrator 的结构化输出"""
    next_steps: List[ExecutionStep] = Field(..., description="下一步任务列表")
    is_complete: bool = Field(False, description="项目是否已完成")
