from typing import TypedDict, TYPE_CHECKING
from pydantic import BaseModel, Field

# 避免循环导入，仅在类型检查时导入
if TYPE_CHECKING:
    from core.models import ProjectState

# --- Unified State Definition ---

class AgentGraphState(TypedDict):
    """
    [Unified State] 全局统一的 Agent 图状态。
    不再使用扁平的 BaseAgentState，而是将所有上下文封装在 project_state 中。
    这使得状态管理更加结构化，并支持 SIG-HA 溯源和向量时钟。
    """
    project_state: 'ProjectState'

# --- Protocol Phase 3: Efficiency Protocols ---

class ContextConstraint(BaseModel):
    """
    [Protocol Phase 3] 动态上下文剪枝协议
    定义了节点在执行时对 Token 消耗的约束条件。
    """
    max_history_steps: int = Field(default=10, description="保留最近多少轮详细对话")
    max_token_budget: int = Field(default=8000, description="该节点的 Context Window 最大 Token 限制")
    
    pruning_strategy: str = Field(
        default="summary_only", 
        description="剪枝策略: 'fifo' (先进先出) | 'summary_only' (只保留摘要) | 'smart_selection' (RAG 筛选)"
    )

    class Config:
        arbitrary_types_allowed = True
