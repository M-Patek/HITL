from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# =======================================================
# 0. Artifact Definitions (New)
# =======================================================

class ResearchArtifact(BaseModel):
    """Researcher 产出的结构化数据"""
    sources: List[str] = Field(default_factory=list, description="来源 URL 列表")
    summary: str = Field(..., description="研究摘要")
    key_facts: List[str] = Field(default_factory=list, description="关键事实列表")

class CodeArtifact(BaseModel):
    """Coding Crew 产出的结构化代码包"""
    files: Dict[str, str] = Field(default_factory=dict, description="文件内容 (Filename -> Content)")
    language: str = Field(..., description="主要编程语言")
    dependencies: List[str] = Field(default_factory=list, description="依赖库列表")

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
    
    # [New] 图片输入支持
    image_data: Optional[str] = Field(None, description="用户上传的图片 (Base64 编码字符串)")
    
    # 产出数据 (Artifacts)
    # [Legacy] 保留旧字段以向后兼容，但建议逐步迁移到 artifacts
    research_summary: Optional[str] = Field(None, description="Researcher 的研究摘要")
    code_blocks: Dict[str, str] = Field(default_factory=dict, description="Coding Crew 生成的代码 (Key=模块名)")
    final_report: Optional[str] = Field(None, description="最终交付物 (报告、文章或数据分析)")
    
    # [New] 统一 Artifact 仓库
    artifacts: Dict[str, Any] = Field(default_factory=dict, description="结构化产出物仓库 (Key=Type/ID)")
    
    # 错误追踪与自愈
    last_error: Optional[str] = Field(None, description="最近一次发生的系统错误")
    user_feedback_queue: Optional[str] = Field(None, description="用户实时反馈，若存在则触发中断")
    
    # 流程控制
    next_step: Optional[Dict[str, str]] = Field(None, description="下一步执行指令 (包含 agent_name, instruction)")
    router_decision: Literal["continue", "finish", "human"] = Field("continue", description="路由决策")
    full_chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="完整对话历史")
