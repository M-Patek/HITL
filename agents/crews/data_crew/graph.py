from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from agents.crews.data_crew.state import DataCrewState
from agents.crews.data_crew.nodes import DataCrewNodes

def route_analysis(state: DataCrewState) -> str:
    status = state.get("review_status", "reject")
    count = state.get("iteration_count", 0)
    
    if status == "approve":
        print("✅ [Data Crew] 分析报告定稿。")
        return "end"
    elif count >= 3: 
        print("⚠️ [Data Crew] 达到最大迭代限制，强制提交。")
        return "end"
    else:
        return "retry"

def build_data_crew_graph(rotator: GeminiKeyRotator) -> StateGraph:
    nodes = DataCrewNodes(rotator)
    workflow = StateGraph(DataCrewState)
    
    workflow.add_node("scientist", nodes.scientist_node)
    workflow.add_node("analyst", nodes.analyst_node)
    
    workflow.set_entry_point("scientist")
    workflow.add_edge("scientist", "analyst")
    
    workflow.add_conditional_edges("analyst", route_analysis, {"retry": "scientist", "end": END})
    
    return workflow.compile()
