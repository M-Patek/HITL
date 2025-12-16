from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from core.models import AgentGraphState # 引用主图的状态
from agents.crews.coding_crew.state import CodingCrewState
from agents.crews.coding_crew.nodes import CodingCrewNodes

def route_review(state: CodingCrewState):
    """决定下一步走向：通过则结束，不通过则回退给 Coder"""
    status = state.get("review_status", "reject")
    count = state.get("iteration_count", 0)
    
    if status == "approve":
        return "end"
    elif count >= 5: # 最大重试 5 次
        print("⚠️ [Coding Crew] 达到最大迭代次数，强制提交。")
        return "end"
    else:
        return "retry"

def build_coding_crew_graph(rotator: GeminiKeyRotator):
    """构建并编译 Coding Crew 子图"""
    
    # 初始化节点逻辑类
    nodes = CodingCrewNodes(rotator)
    
    # 定义子图结构
    workflow = StateGraph(CodingCrewState)
    
    # 添加节点
    workflow.add_node("coder", nodes.coder_node)
    workflow.add_node("reviewer", nodes.reviewer_node)
    
    # 设置入口
    workflow.set_entry_point("coder")
    
    # 定义边
    workflow.add_edge("coder", "reviewer")
    
    workflow.add_conditional_edges(
        "reviewer",
        route_review,
        {
            "retry": "coder",
            "end": END
        }
    )
    
    return workflow.compile()

# =======================================================
# 适配器 (Adapter) - 关键！
# =======================================================
# LangGraph 的子图需要能够接收父图的状态，并返回兼容的状态。
# 下面的函数用于将主图状态 (AgentGraphState) 转换为子图状态 (CodingCrewState)
# 并在子图结束后，将结果合并回主图。

async def coding_crew_adapter(state: AgentGraphState, config):
    """
    这是一个包装器函数，它作为主图中的一个节点运行。
    它负责调用子图，并处理状态的输入/输出映射。
    """
    # 1. 获取子图实例 (这里假设通过某种方式获取，或者在 graph.py 里直接调用 compile)
    # 为了简化，我们通常在 build_agent_workflow 里构建好 subgraph，这里只是演示逻辑
    # 实际在 LangGraph 中，我们直接把 compiled subgraph 当作 node 添加即可。
    # 唯一的难点是状态 schema 不完全一致。
    
    # 简单的做法：子图使用和主图一样的 State，或者主图 State 包含子图所需的字段。
    # 更加解耦的做法：
    pass
