from typing import Dict, Any
from functools import partial
from langgraph.graph import StateGraph, END
from core.crew_registry import crew_registry  # [🔥 Plugin] 引入注册中心
from agents.orchestrator.orchestrator import orchestrator_node
from agents.common_types import BaseAgentState
from core.rotator import GeminiKeyRotator

def build_workflow(rotator: GeminiKeyRotator):
    """
    构建主工作流 (Dynamic & Decoupled)
    """
    # 初始化主图
    workflow = StateGraph(BaseAgentState)
    
    # 1. 添加 Orchestrator 节点
    # 使用 partial 注入 rotator 依赖，因为 LangGraph 节点只能接收 state
    orchestrator_with_rotator = partial(orchestrator_node, rotator=rotator)
    workflow.add_node("orchestrator", orchestrator_with_rotator)
    
    workflow.set_entry_point("orchestrator")
    
    # 2. [🔥 Magic] 动态添加所有已注册的 Crew 节点
    registered_crews = crew_registry.get_all_crews()
    crew_names = []
    
    for name, data in registered_crews.items():
        # 获取子图
        subgraph = data['graph']
        # 将子图作为一个节点加入主图
        workflow.add_node(name, subgraph)
        crew_names.append(name)
        
        # 建立从 Crew 回到 Orchestrator 的边 
        # (这里简化为任务完成后结束，或者可以回到 orchestrator 进行多轮规划)
        workflow.add_edge(name, END)
    
    # 3. 定义动态路由逻辑
    def route_from_orchestrator(state: BaseAgentState):
        next_step = state.get("next_step", "finish")
        
        if next_step in crew_names:
            print(f"🔀 [Router] 动态路由 -> {next_step}")
            return next_step
        elif next_step == "finish":
            return END
        else:
            print(f"⚠️ [Router] 未知目标 '{next_step}'，任务结束。")
            return END

    # 4. 设置 Orchestrator 的条件边
    # 它现在的路由表是动态生成的！
    workflow.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {name: name for name in crew_names} | {"finish": END}
    )
    
    return workflow.compile()
