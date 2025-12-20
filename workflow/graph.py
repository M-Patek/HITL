from typing import Dict, Any, Optional
from functools import partial
from langgraph.graph import StateGraph, END
from core.crew_registry import crew_registry
from agents.orchestrator.orchestrator import orchestrator_node
from agents.planner.planner import planner_node
from agents.common_types import AgentGraphState
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool

def build_agent_workflow(
    rotator: GeminiKeyRotator, 
    memory: VectorMemoryTool, 
    search: GoogleSearchTool, 
    checkpointer: Any = None
):
    """
    构建主工作流 (Dynamic & Dependency Injected)
    [Fix] 恢复正确的函数签名以匹配 api_server.py。
    [Feature] 集成 Planner 节点作为系统入口。
    """
    # 初始化主图
    workflow = StateGraph(AgentGraphState)
    
    # 1. 添加核心系统节点 (Injecting Dependencies)
    # Orchestrator 需要 rotator
    orchestrator_with_deps = partial(orchestrator_node, rotator=rotator)
    # Planner 也需要 rotator
    planner_with_deps = partial(planner_node, rotator=rotator)
    
    workflow.add_node("planner", planner_with_deps)
    workflow.add_node("orchestrator", orchestrator_with_deps)
    
    # 2. 设置入口: 先规划，再调度
    workflow.set_entry_point("planner")
    
    # 3. 连接 Planner -> Orchestrator
    workflow.add_edge("planner", "orchestrator")
    
    # 4. 动态构建并添加所有已注册的 Crew 节点
    registered_crews = crew_registry.get_all_crews()
    crew_names = []
    
    for name, data in registered_crews.items():
        # 获取构建函数
        builder = data.get('builder')
        if builder:
            try:
                # [Dependency Injection]
                # 目前所有 Crew 的 builder 至少支持传入 rotator。
                subgraph = builder(rotator)
                
                workflow.add_node(name, subgraph)
                crew_names.append(name)
                
                # 建立从 Crew 回到 Orchestrator 的边 (目前简化为结束，由 Router 控制逻辑)
                workflow.add_edge(name, END)
                print(f"   ➕ 子图装载: {name}")
            except Exception as e:
                print(f"   ❌ 子图构建失败 {name}: {e}")
    
    # 5. 定义动态路由逻辑
    def route_from_orchestrator(state: AgentGraphState):
        project_state = state["project_state"]
        next_step_data = project_state.next_step
        
        target = "finish"
        if isinstance(next_step_data, dict):
            target = next_step_data.get("agent_name") or next_step_data.get("next_agent", "finish")
        elif isinstance(next_step_data, str):
            target = next_step_data
        
        if target in crew_names:
            print(f"🔀 [Router] 动态路由 -> {target}")
            return target
        elif target == "finish":
            return END
        else:
            print(f"⚠️ [Router] 未知目标 '{target}'，任务结束。")
            return END

    # 6. 设置 Orchestrator 的条件边
    workflow.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {name: name for name in crew_names} | {"finish": END}
    )
    
    return workflow.compile(checkpointer=checkpointer)
