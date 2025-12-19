from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

# =======================================================
# 基础工件模型 (Artifacts)
# =======================================================

class ResearchArtifact(BaseModel):
    summary: str
    key_facts: List[str]
    sources: List[str]

class CodeArtifact(BaseModel):
    code: str
    language: str = "python"
    filename: str = "script.py"

class ArtifactVersion(BaseModel):
    """
    [Phase 4] Version Control System for Artifacts
    用于追踪工件的版本历史 (Vector Clock Support)
    """
    trace_id: str
    node_id: str
    vector_clock: Dict[str, int]
    type: str  # 'image', 'code', 'report'
    content: Any
    label: str
    timestamp: float = Field(default_factory=lambda: __import__("time").time())

# =======================================================
# 全局项目状态 (ProjectState)
# =======================================================

class ProjectState(BaseModel):
    """
    全局项目状态，在所有 Agent 之间流转的核心数据结构。
    包含了任务信息、对话历史、SIG-HA 签名和所有小队的产出。
    """
    # --- 基础信息 ---
    task_id: str
    user_input: str
    image_data: Optional[str] = None  # Base64 编码的输入图片
    
    # --- 状态机控制 ---
    next_step: Optional[Dict[str, str]] = None  # e.g., {"agent_name": "coding_crew", "instruction": "..."}
    plan: str = ""  # 全局计划文本
    active_node_id: str = "orchestrator"
    
    # --- 记忆与历史 ---
    # 兼容 OpenAI/LangChain 格式的消息历史
    full_chat_history: List[Dict[str, Any]] = Field(default_factory=list)
    # LangChain Message 对象列表 (用于图计算内部)
    messages: List[BaseMessage] = Field(default_factory=list)
    
    # --- 产出物 (Artifacts) ---
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    # 结构: {"research": {...}, "code": "...", "images": [{"filename":..., "data":...}]}
    
    artifact_history: List[ArtifactVersion] = Field(default_factory=list)

    # --- 反馈队列 ---
    user_feedback_queue: Optional[str] = None
    final_report: Optional[str] = None

    # --- 并发控制 (Vector Clock) ---
    vector_clock: Dict[str, int] = Field(default_factory=lambda: {"main": 0})
    prefetch_cache: Dict[str, Any] = Field(default_factory=dict)

    # --- SIG-HA 全息签名 (Security) ---
    trace_t: str = "0"
    trace_depth: int = 0
    trace_history: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def get_active_node(self):
        """Helper to simulate node retrieval based on active_node_id"""
        # 这是一个简化的 helper，实际逻辑可能更复杂
        return type("NodeMock", (), {"instruction": self.next_step.get("instruction", "") if self.next_step else "", "local_history": self.full_chat_history})()
