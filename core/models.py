from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict, Union
from langchain_core.messages import BaseMessage

# 定义统一的Agent状态模型
class AgentState(BaseModel):
    """
    HITL System Global State
    
    Includes SIG-HA cryptographic tracing fields for verifiable history.
    """
    messages: List[BaseMessage] = Field(default_factory=list)
    next_step: str = Field(default="end", description="Next agent/node to execute")
    plan: str = Field(default="", description="Current execution plan")
    
    # Context Data
    user_input: str = Field(default="")
    research_data: Dict[str, Any] = Field(default_factory=dict)
    code_snippets: List[str] = Field(default_factory=list)
    
    # Flags
    is_coding_required: bool = Field(default=False)
    human_feedback: Optional[str] = Field(default=None)
    
    # -------------------------------------------------------------------------
    # SIG-HA Holographic Tracing Fields
    # -------------------------------------------------------------------------
    trace_t: str = Field(
        default="0", 
        description="The current cryptographic accumulator value (Holographic Fingerprint)"
    )
    trace_depth: int = Field(
        default=0, 
        description="Current topological depth of the execution trace"
    )
    trace_history: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Audit log of trace transitions for visualization"
    )

    class Config:
        arbitrary_types_allowed = True
