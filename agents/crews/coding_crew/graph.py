from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from agents.crews.coding_crew.state import CodingCrewState
from agents.crews.coding_crew.nodes import CodingCrewNodes

def route_review(state: CodingCrewState) -> str:
    """Coding Crew 内部路由逻辑"""
    status = state.get("review_status", "reject")
    count = state.get("iteration_count", 0)
    
    if status == "approve":
        print("✅ [Coding Crew] 代码通过审查。")
        return "end"
    elif count >= 5: # 最大重试次数
        print("⚠️ [Coding Crew] 达到最大迭代限制，强制提交。")
        return "end"
    else:
        return "retry"

def build_coding_crew_graph(rotator: GeminiKeyRotator) -> StateGraph:
    nodes = CodingCrewNodes(rotator)
    workflow = StateGraph(CodingCrewState)
    
    # 定义节点
    workflow.add_node("coder", nodes.coder_node)
    workflow.add_node("executor", nodes.executor_node) # [New] 执行节点
    workflow.add_node("reviewer", nodes.reviewer_node)
    
    # 定义流程
    workflow.set_entry_point("coder")
    
    # 流程变更为: Coder -> Executor -> Reviewer
    workflow.add_edge("coder", "executor")
    workflow.add_edge("executor", "reviewer")
    
    workflow.add_conditional_edges(
        "reviewer",
        route_review,
        {
            "retry": "coder",
            "end": END
        }
    )
    
    return workflow.compile()
