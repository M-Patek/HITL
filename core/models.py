from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

# --- Enums & Helpers ---

class TaskLevel(str):
    PROJECT = "project"
    SUBTREE = "subtree"
    LEAF = "leaf"

class TaskStatus(str):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

class TaskPhase(str):
    INITIAL_PLAN = "INITIAL_PLAN"
    SUB_TASK_EXECUTION = "SUB_TASK_EXECUTION"
    REGRESSION_SUMMARY = "REGRESSION_SUMMARY"

# --- Protocol Models ---

class StageProtocol(BaseModel):
    current_phase: str = Field(default=TaskPhase.INITIAL_PLAN)
    meta_data: Dict[str, Any] = Field(default_factory=dict)

class SubTreeSummary(BaseModel):
    task_id: str
    execution_path: List[str] = Field(default_factory=list)
    final_artifact_ref: Optional[Dict[str, Any]] = None
    semantic_digest: str

class ToolCallRecord(BaseModel):
    tool_name: str
    input_params: Dict[str, Any]
    output_result: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: Literal["success", "error"] = "success"

class ArtifactVersion(BaseModel):
    """
    [Phase 3 New] 产物版本控制对象
    """
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # [Phase 4] 全链路追踪字段
    trace_id: Optional[str] = None 
    node_id: str
    
    type: Literal["code", "image", "report"]
    content: Any # Code string or Image data dict
    label: str = "v1"

class TaskNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    level: str = TaskLevel.LEAF
    status: str = TaskStatus.PENDING
    stage_protocol: StageProtocol = Field(default_factory=StageProtocol)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    instruction: str
    reasoning: str = ""
    local_history: List[Dict[str, Any]] = Field(default_factory=list)
    semantic_summary: str = ""
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    children: List['TaskNode'] = Field(default_factory=list)

    def add_child(self, child: 'TaskNode'):
        child.parent_id = self.node_id
        self.children.append(child)
        
    def get_context_str(self) -> str:
        ctx = f"Node: {self.instruction} (Status: {self.status}, Phase: {self.stage_protocol.current_phase})\n"
        if self.semantic_summary:
            ctx += f"Summary: {self.semantic_summary}\n"
        return ctx

# --- Project State (Root) ---

class ProjectState(BaseModel):
    task_id: str
    root_node: TaskNode
    active_node_id: str
    node_map: Dict[str, TaskNode] = Field(default_factory=dict)
    
    # Global Context
    artifacts: Dict[str, Any] = {}
    code_blocks: Dict[str, str] = {}
    image_data: Optional[str] = None
    
    # [Speculative] Prefetch Cache
    prefetch_cache: Dict[str, str] = Field(default_factory=dict)
    
    # [Version Control] Artifact History
    artifact_history: List[ArtifactVersion] = Field(default_factory=list)
    
    # Flow Control
    router_decision: str = "continue"
    next_step: Optional[Dict[str, Any]] = None 
    user_feedback_queue: Optional[str] = None
    last_error: Optional[str] = None
    final_report: Optional[str] = None
    
    @property
    def user_input(self) -> str:
        return self.root_node.instruction

    @classmethod
    def init_from_task(cls, task_desc: str, task_id: str, image_data: Optional[str] = None) -> 'ProjectState':
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
        parent = self.node_map.get(parent_id)
        if parent:
            parent.add_child(child_node)
            self.node_map[child_node.node_id] = child_node
        else:
            raise ValueError(f"Parent node {parent_id} not found")

class TaskRequest(BaseModel):
    user_input: str
    thread_id: Optional[str] = None
