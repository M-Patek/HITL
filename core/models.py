from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class TaskRequest(BaseModel):
    """
    用户发起任务的请求模型
    """
    user_input: str = Field(..., description="用户的原始任务描述")
    thread_id: Optional[str] = Field(None, description="会话/线程 ID，用于支持多轮对话或中断恢复")

class FeedbackRequest(BaseModel):
    """
    [New] 用户反馈专用请求模型
    """
    thread_id: str = Field(..., description="目标线程 ID")
    feedback: str = Field(..., description="用户的反馈内容或指令修改")

class StreamEvent(BaseModel):
    """
    流式输出的事件模型 (Server-Sent Events 结构)
    """
    event_type: str = Field(..., description="事件类型 (e.g., 'token', 'log', 'error', 'finish')")
    data: Dict[str, Any] = Field(default_factory=dict, description="事件的具体载荷数据")
