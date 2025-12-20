from typing import Any
from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from agents.crews.coding_crew.state import CodingCrewState
from agents.crews.coding_crew.nodes import CodingCrewNodes

def route_review(state: CodingCrewState) -> str:
    """Coding Crew 内部路由逻辑"""
    status = state.get("review_status", "reject")
    count = state.get("iteration_count", 0)
    
    if status == "approve":
        return "summarize"
    elif count >= 5: 
        return "summarize"
    else:
        return "retry"

def build_coding_crew_graph(rotator: GeminiKeyRotator, checkpointer: Any = None) -> StateGraph:
    nodes = CodingCrewNodes(rotator)
    workflow = StateGraph(CodingCrewState)
    
    workflow.add_node("coder", nodes.coder_node)
    workflow.add_node("executor", nodes.executor_node)
    workflow.add_node("reviewer", nodes.reviewer_node)
    workflow.add_node("summarizer", nodes.summarizer_node)
    
    workflow.set_entry_point("coder")
    
    workflow.add_edge("coder", "executor")
    workflow.add_edge("executor", "reviewer")
    
    workflow.add_conditional_edges(
        "reviewer",
        route_review,
        {
            "retry": "coder",
            "summarize": "summarizer"
        }
    )
    
    workflow.add_edge("summarizer", END)
    
    # [Update] 传入 checkpointer 以支持子图的历史记录查询
    return workflow.compile(checkpointer=checkpointer)
