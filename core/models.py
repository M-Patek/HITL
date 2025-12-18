from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

# --- Enums & Helpers ---

class TaskLevel(str):
    PROJECT = "project"   # 根任务
    SUBTREE = "subtree"   # 子任务组 (如 Data Crew)
    LEAF = "leaf"         # 原子执行节点 (如 Search, Code Gen)

class TaskStatus(str):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

# --- Node Components ---

class ToolCallRecord(BaseModel):
    """记录工具调用的元数据"""
    tool_name: str
    input_params: Dict[str, Any]
    output_result: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: Literal["success", "error"] = "success"

class TaskNode(BaseModel):
    """
    [Core] 递归任务节点
    构成了 ProjectState 的骨架。每个节点代表一个任务或子任务。
    """
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    
    # 节点属性
    level: Literal["project", "subtree", "leaf"] = TaskLevel.LEAF
    status: Literal["pending", "active", "completed", "failed", "blocked"] = TaskStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # 核心内容
    instruction: str = Field(..., description="该节点的具体任务指令")
    reasoning: str = Field("", description="Orchestrator 创建该节点时的思考过程")
    
    # [Memory] 该节点的局部历史与摘要
    # 取代了全局扁平的 chat_history
    local_history: List[Dict[str, Any]] = Field(default_factory=list)
    semantic_summary: str = Field("", description="RAPTOR 风格的阶段性摘要")
    
    # [Execution] 工具调用记录
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    
    # [Structure] 子节点
    children: List[TaskNode] = Field(default_factory=list)

    def add_child(self, child: 'TaskNode'):
        child.parent_id = self.node_id
        self.children.append(child)
        
    def get_context_str(self) -> str:
        """获取该节点的上下文摘要（用于 Prompt 注入）"""
        ctx = f"Node: {self.instruction} (Status: {self.status})\n"
        if self.semantic_summary:
            ctx += f"Summary: {self.semantic_summary}\n"
        return ctx

# --- Project State (Root) ---

class ProjectState(BaseModel):
    """
    全局项目状态对象 (Tree-based)
    不再依赖扁平历史，而是维护一棵任务树。
    """
    task_id: str
    
    # [Tree Structure]
    root_node: TaskNode
    active_node_id: str
    
    # [Index] 扁平化索引，用于 O(1) 查找节点
    node_map: Dict[str, TaskNode] = Field(default_factory=dict)
    
    # [Global Context] 依然保留一些全局共享的资源
    artifacts: Dict[str, Any] = {}
    code_blocks: Dict[str, str] = {}
    image_data: Optional[str] = None
    
    # [Flow Control]
    router_decision: str = "continue"
    next_step: Optional[Dict[str, Any]] = None # 兼容旧逻辑，指向下一个 action
    user_feedback_queue: Optional[str] = None
    last_error: Optional[str] = None
    final_report: Optional[str] = None
    
    # [Compat] 兼容层：如果有些旧代码还在读 user_input
    @property
    def user_input(self) -> str:
        return self.root_node.instruction

    @classmethod
    def init_from_task(cls, task_desc: str, task_id: str, image_data: Optional[str] = None) -> 'ProjectState':
        """初始化一个新的项目树"""
        root = TaskNode(
            level=TaskLevel.PROJECT,
            instruction=task_desc,
            status=TaskStatus.ACTIVE,
            reasoning="Root user task"
        )
        instance = cls(
            task_id=task_id,
            root_node=root,
            active_node_id=root.node_id,
            node_map={root.node_id: root},
            image_data=image_data
        )
        return instance

    def get_active_node(self) -> Optional[TaskNode]:
        return self.node_map.get(self.active_node_id)

    def add_node(self, parent_id: str, child_node: TaskNode):
        """注册新节点到树和索引中"""
        parent = self.node_map.get(parent_id)
        if parent:
            parent.add_child(child_node)
            self.node_map[child_node.node_id] = child_node
        else:
            raise ValueError(f"Parent node {parent_id} not found")

# --- Legacy/API Models (Keep for API server compatibility if needed) ---
# ... (可以保留 StreamEvent 等，视需求而定)
class TaskRequest(BaseModel):
    user_input: str
    thread_id: Optional[str] = None

class FeedbackRequest(BaseModel):
    thread_id: str
    feedback: str

class ResearchArtifact(BaseModel):
    summary: str
    key_facts: List[str]
    sources: List[str]
