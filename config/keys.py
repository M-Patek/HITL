from typing import TypedDict, List, Dict, Any

# =======================================================
# 通用状态定义 (Base Types)
# =======================================================

class BaseAgentState(TypedDict):
    """
    基础 Agent 状态接口。
    所有子图的状态定义 (CrewState) 都应该包含这些基础字段，
    以便于在主图和子图之间传递上下文。
    """
    task_id: str
    user_input: str
    full_chat_history: List[Dict[str, Any]]

class BaseAgent:
    """所有 Agent 的基类，负责持有 LLM Client"""
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

# 类型别名定义
State = Dict[str, Any]
GraphDefinition = Any  # [Fix] 将 GraphDefinition 定义在这里，打破循环依赖
