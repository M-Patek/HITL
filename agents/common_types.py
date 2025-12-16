from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

# =======================================================
# 定义基础的状态类型，方便各个模块复用
# =======================================================

class BaseAgentState(TypedDict):
    """基础 Agent 状态，包含所有 Agent 都可能需要访问的字段"""
    task_id: str
    user_input: str
    full_chat_history: List[Dict[str, Any]]
