import random
import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from langgraph.checkpoint.memory import MemorySaver

from config.keys import GATEWAY_API_BASE, GATEWAY_SECRET, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from core.models import ProjectState
from workflow.graph import build_agent_workflow

# --- 日志 ---
logger = logging.getLogger("Brain-Engine")

# --- 持久化检查点：这是工作流能够恢复的灵魂 ---
GLOBAL_CHECKPOINTER = MemorySaver()

# 初始化大脑核心组件
_rotator = GeminiKeyRotator(GATEWAY_API_BASE, GATEWAY_SECRET)
_memory_tool = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
_search_tool = GoogleSearchTool()

# 构建 Agent 工作流图 (必须注入全量工具)
_app = build_agent_workflow(_rotator, _memory_tool, _search_tool, checkpointer=GLOBAL_CHECKPOINTER)

async def run_workflow(user_input: str, thread_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    """
    全逻辑引擎：处理新任务初始化、断点恢复、反馈注入、以及 Artifacts 实时推送。
    """
    if _app is None:
        yield {"event_type": "error", "data": "Workflow Engine not initialized."}
        return

    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. 状态深度检查
    snapshot = _app.get_state(config)
    current_input = None
    
    if not snapshot.values:
        # --- 情况 A: 新任务 ---
        ps = ProjectState(
            task_id=f"T-{thread_id[-4:]}",
            user_input=user_input,
            full_chat_history=[{"role": "user", "parts": [{"text": user_input}]}]
        )
        current_input = {"project_state": ps}
        yield {"event_type": "status", "data": f"🚀 S.W.A.R.M. 任务启动成功: {ps.task_id}"}
    else:
        # --- 情况 B: 中断恢复 (HITL 核心逻辑) ---
        if snapshot.next:
            node_at = snapshot.next[0]
            yield {"event_type": "status", "data": f"🔄 正在从中断点 [{node_at}] 恢复..."}
            
            # 补全逻辑：如果恢复时有用户输入，将其作为 Feedback 注入状态
            if user_input:
                ps = snapshot.values.get('project_state')
                if ps:
                    ps.user_feedback_queue = user_input
                    # 关键：更新状态库中的值
                    _app.update_state(config, {"project_state": ps})
                    yield {"event_type": "feedback", "data": "用户反馈已成功注入工作流状态喵。"}
            current_input = None # 恢复任务不需要重新传入 input
        else:
            yield {"event_type": "warning", "data": "该任务已执行完毕喵。"}
            return

    # 2. 执行与流式推送
    try:
        # 使用 stream_mode="values" 获取完整的状态更新
        async for event in _app.astream(current_input, config=config, stream_mode="values"):
            if 'project_state' not in event: continue
            ps = event['project_state']
            
            # A. 错误处理
            if ps.last_error:
                yield {"event_type": "error", "data": ps.last_error}
                continue
            
            # B. 决策变更推送
            yield {
                "event_type": "update", 
                "data": {
                    "status": ps.router_decision, 
                    "agent": ps.next_step.get("agent_name") if ps.next_step else "SYSTEM"
                }
            }
            
            # C. 实时产出：代码块推送 (Canvas 协作核心)
            if ps.code_blocks:
                # 只推送最新生成的代码块
                latest_agent = list(ps.code_blocks.keys())[-1]
                yield {"event_type": "artifact_code", "data": ps.code_blocks[latest_agent]}
            
            # D. 实时产出：报告推送
            if ps.final_report:
                yield {"event_type": "final_report", "data": ps.final_report}

        # 3. 运行结束后的中断判断
        final_snapshot = _app.get_state(config)
        if final_snapshot.next:
            yield {
                "event_type": "interrupt", 
                "data": {
                    "node": final_snapshot.next[0],
                    "msg": "工作流已达到审批点，请在下方回复以继续喵。"
                }
            }
        else:
            yield {"event_type": "finish", "data": "✅ 任务已全流程圆满完成喵！"}

    except Exception as e:
        logger.error(f"💥 Engine Crash: {e}", exc_info=True)
        yield {"event_type": "error", "data": f"内部引擎崩溃: {str(e)}"}
