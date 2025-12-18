from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- Request Models ---

class TaskRequest(BaseModel):
    user_input: str = Field(..., description="用户的原始任务描述")
    thread_id: Optional[str] = Field(None, description="会话/线程 ID")

class FeedbackRequest(BaseModel):
    thread_id: str = Field(..., description="目标线程 ID")
    feedback: str = Field(..., description="用户的反馈内容")

class StreamEvent(BaseModel):
    event_type: str
    data: Dict[str, Any]

# --- State Models ---

class ResearchArtifact(BaseModel):
    summary: str
    key_facts: List[str]
    sources: List[str]

class ProjectState(BaseModel):
    """
    全局项目状态对象 (The Source of Truth)
    """
    task_id: str
    user_input: str
    
    # [New] 长时记忆摘要 (Infinite Memory)
    long_term_memory: str = Field("", description="对早期对话历史的压缩摘要")
    
    full_chat_history: List[Dict[str, Any]] = []
    
    # 结构化产出
    artifacts: Dict[str, Any] = {}
    code_blocks: Dict[str, str] = {}
    final_report: Optional[str] = None
    
    # 流程控制
    last_error: Optional[str] = None
    router_decision: str = "continue"
    next_step: Optional[Dict[str, Any]] = None
    user_feedback_queue: Optional[str] = None
    
    # 多模态支持
    image_data: Optional[str] = None
