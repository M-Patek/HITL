from langgraph.graph import StateGraph, END
from core.rotator import GeminiKeyRotator
from agents.crews.content_crew.state import ContentCrewState
from agents.crews.content_crew.nodes import ContentCrewNodes

def route_content(state: ContentCrewState) -> str:
    if state.get("review_status") == "approve":
        print("✅ [Content Crew] 内容定稿。")
        return "end"
    
    if state.get("iteration_count", 0) >= 3: 
        print("⚠️ [Content Crew] 达到最大迭代限制，强制定稿。")
        return "end"
        
    return "retry"

def build_content_crew_graph(rotator: GeminiKeyRotator) -> StateGraph:
    nodes = ContentCrewNodes(rotator)
    workflow = StateGraph(ContentCrewState)
    
    workflow.add_node("writer", nodes.writer_node)
    workflow.add_node("editor", nodes.editor_node)
    
    workflow.set_entry_point("writer")
    workflow.add_edge("writer", "editor")
    
    workflow.add_conditional_edges("editor", route_content, {"retry": "writer", "end": END})
    
    return workflow.compile()
