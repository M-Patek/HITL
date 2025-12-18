from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- Base States ---

class BaseAgentState(TypedDict):
    """基础 Agent 状态字典"""
    task_id: str
    user_input: str
    current_instruction: str
    # History
    full_chat_history: List[Dict[str, Any]]
    # Feedback
    review_status: str
    review_feedback: str
    # Artifacts
    generated_code: str
    image_artifacts: List[Dict[str, str]]
    final_output: str

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
