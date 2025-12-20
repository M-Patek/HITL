from typing import List, Dict, Any, Optional, Union
import time
from enum import Enum
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

# =======================================================
# 状态枚举与节点定义
# =======================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

class StageProtocol(BaseModel):
    """记录节点当前处于哪个生命周期阶段"""
    current_phase: str = "INITIAL_PLAN"

class TaskNode(BaseModel):
    """
    任务节点模型，用于构建任务树。
    """
    node_id: str
    instruction: str
    status: TaskStatus = TaskStatus.PENDING
    level: int = 0
    parent_id: Optional[str] = None
    semantic_summary: str = ""
    # 节点的局部对话历史
    local_history: List[Dict[str, Any]] = Field(default_factory=list)
    # 节点的协议状态
    stage_protocol: StageProtocol = Field(default_factory=StageProtocol)

    class Config:
        arbitrary_types_allowed = True

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
    Version Control System for Artifacts
    用于追踪工件的版本历史 (Vector Clock Support)
    """
    trace_id: Optional[str] = None
    node_id: str
    vector_clock: Dict[str, int]
    type: str  # 'image', 'code', 'report'
    content: Any
    label: str
    timestamp: float = Field(default_factory=lambda: time.time())

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
    
    # --- 任务图结构 ---
    node_map: Dict[str, TaskNode] = Field(default_factory=dict)
    root_node: Optional[TaskNode] = None
    active_node_id: str = "root"

    # --- 状态机控制 ---
    next_step: Optional[Dict[str, Any]] = None  # e.g., {"agent_name": "coding_crew", "instruction": "..."}
    router_decision: str = "orchestrator" # router decision buffer
    plan: str = ""  # 全局计划文本 (JSON String from Planner)
    
    # --- 记忆与历史 ---
    # 兼容 OpenAI/LangChain 格式的消息历史 (全局)
    full_chat_history: List[Dict[str, Any]] = Field(default_factory=list)
    # LangChain Message 对象列表 (用于图计算内部)
    messages: List[BaseMessage] = Field(default_factory=list)
    
    # --- 产出物 (Artifacts) ---
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    # 结构: {"research": {...}, "code": "...", "images": [{"filename":..., "data":...}]}
    code_blocks: Dict[str, str] = Field(default_factory=dict) # 专门存储各Agent的代码片段
    
    artifact_history: List[ArtifactVersion] = Field(default_factory=list)

    # --- 反馈队列 ---
    user_feedback_queue: Optional[str] = None
    final_report: Optional[str] = None
    last_error: Optional[str] = None

    # --- 并发控制 (Vector Clock) ---
    vector_clock: Dict[str, int] = Field(default_factory=lambda: {"main": 0})
    prefetch_cache: Dict[str, Any] = Field(default_factory=dict)

    # --- SIG-HA 全息签名 (Security) ---
    trace_t: str = "0"
    trace_depth: int = 0
    trace_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    # --- Research Summary ---
    research_summary: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def init_from_task(cls, user_input: str, task_id: str) -> "ProjectState":
        """初始化一个新的项目状态，包含根节点"""
        root = TaskNode(node_id="root", instruction=user_input, status=TaskStatus.IN_PROGRESS)
        return cls(
            task_id=task_id,
            user_input=user_input,
            root_node=root,
            node_map={"root": root},
            active_node_id="root"
        )

    def get_active_node(self) -> Optional[TaskNode]:
        """获取当前激活的节点对象"""
        return self.node_map.get(self.active_node_id)
