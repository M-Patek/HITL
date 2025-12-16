from typing import TypedDict, List, Dict, Any

# =======================================================
# 通用状态定义 (Base Types)
# =======================================================
# 这里定义了所有 Agent 或 Subgraph 可能共用的基础字段。

class BaseAgentState(TypedDict):
    """
    基础 Agent 状态接口。
    所有子图的状态定义 (CrewState) 都应该包含这些基础字段，
    以便于在主图和子图之间传递上下文。
    """
    task_id: str
    user_input: str
    full_chat_history: List[Dict[str, Any]]
