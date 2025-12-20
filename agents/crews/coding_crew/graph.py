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
        # 超过最大次数也强制总结，避免死循环 (Fail gracefully)
        print("   ⚠️ 达到最大重试次数，强制结束。")
        return "summarize"
    else:
        # [🔥 Change] 失败了先去反思，而不是直接重写
        return "reflect"

def build_coding_crew_graph(rotator: GeminiKeyRotator, checkpointer: Any = None) -> StateGraph:
    nodes = CodingCrewNodes(rotator)
    workflow = StateGraph(CodingCrewState)
    
    # 添加节点
    workflow.add_node("coder", nodes.coder_node)
    workflow.add_node("executor", nodes.executor_node)
    workflow.add_node("reviewer", nodes.reviewer_node)
    # [🔥 New] 添加反思节点
    workflow.add_node("reflector", nodes.reflector_node) 
    workflow.add_node("summarizer", nodes.summarizer_node)
    
    # 设置入口
    workflow.set_entry_point("coder")
    
    # 构建边
    workflow.add_edge("coder", "executor")
    workflow.add_edge("executor", "reviewer")
    
    # 条件路由：Reviewer -> (Reflect or Summarize)
    workflow.add_conditional_edges(
        "reviewer",
        route_review,
        {
            "reflect": "reflector", 
            "summarize": "summarizer"
        }
    )
    
    # [🔥 New] Reflector -> Coder (Reflector 把策略传给 Coder)
    workflow.add_edge("reflector", "coder")
    
    workflow.add_edge("summarizer", END)
    
    return workflow.compile(checkpointer=checkpointer)

# 默认图实例，用于 Registry 导入
# 注意：实际运行时会由主程序传入真实的 rotator，这里仅为占位或测试使用
graph = build_coding_crew_graph(GeminiKeyRotator([]))
