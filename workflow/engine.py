import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, List

from langgraph.checkpoint.memory import MemorySaver

from config.keys import GATEWAY_API_BASE, GATEWAY_SECRET, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from core.models import ProjectState, TaskNode
from workflow.graph import build_agent_workflow
from core.logger_setup import node_id_ctx # [New] Context management

logger = logging.getLogger("Brain-Engine")
GLOBAL_CHECKPOINTER = MemorySaver()

_rotator = GeminiKeyRotator(GATEWAY_API_BASE, GATEWAY_SECRET)
_memory_tool = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
_search_tool = GoogleSearchTool()
_app = build_agent_workflow(_rotator, _memory_tool, _search_tool, checkpointer=GLOBAL_CHECKPOINTER)

def get_breadcrumbs(state: ProjectState) -> List[Dict[str, str]]:
    """[Observability] 构建面包屑导航数据"""
    breadcrumbs = []
    current_id = state.active_node_id
    
    while current_id:
        node = state.node_map.get(current_id)
        if not node: break
        
        breadcrumbs.append({
            "id": node.node_id,
            "label": node.instruction[:30], # 截断显示
            "level": node.level,
            "status": node.status
        })
        current_id = node.parent_id
        
    return list(reversed(breadcrumbs))

async def run_workflow(user_input: str, thread_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    if _app is None:
        yield {"event_type": "error", "data": "Workflow Engine not initialized."}
        return

    config = {"configurable": {"thread_id": thread_id}}
    snapshot = _app.get_state(config)
    current_input = None
    
    # 1. 初始化或恢复
    if not snapshot.values:
        # [New] 使用树状结构初始化
        ps = ProjectState.init_from_task(user_input, f"T-{thread_id[-4:]}")
        current_input = {"project_state": ps}
        yield {"event_type": "status", "data": f"🚀 S.W.A.R.M. Tree Initialized: {ps.task_id}"}
    else:
        if snapshot.next:
            node_at = snapshot.next[0]
            yield {"event_type": "status", "data": f"🔄 Resuming from [{node_at}]..."}
            if user_input:
                ps = snapshot.values.get('project_state')
                if ps:
                    ps.user_feedback_queue = user_input
                    _app.update_state(config, {"project_state": ps})
                    yield {"event_type": "feedback", "data": "User feedback injected."}
            current_input = None
        else:
            yield {"event_type": "warning", "data": "Task already completed."}
            return

    # 2. 执行循环
    try:
        async for event in _app.astream(current_input, config=config, stream_mode="values"):
            if 'project_state' not in event: continue
            ps: ProjectState = event['project_state']
            
            # [Observability] 注入当前的 Node ID 到日志上下文
            if ps.active_node_id:
                node_id_ctx.set(ps.active_node_id)
            
            # A. 错误处理
            if ps.last_error:
                yield {"event_type": "error", "data": ps.last_error}
                ps.last_error = None # Clear after reporting
                continue
            
            # B. 决策变更
            yield {
                "event_type": "update", 
                "data": {
                    "status": ps.router_decision, 
                    "agent": ps.next_step.get("agent_name") if ps.next_step else "SYSTEM"
                }
            }
            
            # C. [New] 树状结构更新 (面包屑)
            yield {
                "event_type": "tree_update",
                "data": get_breadcrumbs(ps)
            }
            
            # D. 代码块
            if ps.code_blocks:
                latest_agent = list(ps.code_blocks.keys())[-1]
                yield {"event_type": "artifact_code", "data": ps.code_blocks[latest_agent]}
            
            # E. 报告
            if ps.final_report:
                yield {"event_type": "final_report", "data": ps.final_report}

        # 3. 结束
        final_snapshot = _app.get_state(config)
        if final_snapshot.next:
            yield {
                "event_type": "interrupt", 
                "data": {"node": final_snapshot.next[0], "msg": "Paused for HITL."}
            }
        else:
            yield {"event_type": "finish", "data": "✅ All tasks completed."}

    except Exception as e:
        logger.error(f"💥 Engine Crash: {e}", exc_info=True)
        yield {"event_type": "error", "data": f"Engine Crash: {str(e)}"}
