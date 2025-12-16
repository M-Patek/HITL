from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from agents.crews.data_crew.state import DataCrewState
from agents.crews.data_crew.nodes import DataCrewNodes

def route_analysis(state: DataCrewState):
    """Data Crew 的内部路由逻辑"""
    status = state.get("review_status", "reject")
    count = state.get("iteration_count", 0)
    
    if status == "approve":
        print("✅ [Data Crew] 报告通过审核。")
        return "end"
    elif count >= 3: # 数据分析通常不需要太多的来回拉扯，3次足矣
        print("⚠️ [Data Crew] 达到最大迭代次数，强制提交当前结果。")
        return "end"
    else:
        return "retry"

def build_data_crew_graph(rotator: GeminiKeyRotator):
    """构建 Data Crew 子图"""
    
    # 初始化节点逻辑
    nodes = DataCrewNodes(rotator)
    
    # 定义子图
    workflow = StateGraph(DataCrewState)
    
    # 添加节点
    workflow.add_node("scientist", nodes.scientist_node)
    workflow.add_node("analyst", nodes.analyst_node)
    
    # 设置入口
    workflow.set_entry_point("scientist")
    
    # 定义边：Scientist -> Analyst
    workflow.add_edge("scientist", "analyst")
    
    # 定义条件边：Analyst -> (Retry -> Scientist) OR (End)
    workflow.add_conditional_edges(
        "analyst",
        route_analysis,
        {
            "retry": "scientist",
            "end": END
        }
    )
    
    return workflow.compile()
