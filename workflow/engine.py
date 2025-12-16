import random
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from langgraph.checkpoint.memory import MemorySaver

# 导入配置和工具
from config.keys import GEMINI_API_KEYS, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from core.models import ProjectState
from workflow.graph import build_agent_workflow

# =======================================================
# 全局单例初始化
# =======================================================
# 在 API 服务生命周期内保持状态持久化 (MemorySaver)
# 生产环境应替换为 RedisSaver 或 PostgresSaver
GLOBAL_CHECKPOINTER = MemorySaver()

# 初始化共享工具实例
# 避免每次请求都重新建立 Pinecone 连接或 API 客户端
_rotator = GeminiKeyRotator(GEMINI_API_KEYS)
_memory_tool = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
_search_tool = GoogleSearchTool()

# 预编译 Graph
# LangGraph 的 CompiledGraph 是无状态的定义，状态由 Checkpointer 管理
_app = build_agent_workflow(_rotator, _memory_tool, _search_tool, checkpointer=GLOBAL_CHECKPOINTER)

async def workflow_stream_generator(
    user_input: str,
    thread_id: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    工作流执行引擎的核心生成器。
    
    Args:
        user_input: 用户的输入或反馈
        thread_id: 会话 ID，用于状态持久化和恢复
        
    Yields:
        Dict: 包含 event_type 和 payload 的事件对象
    """
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. 状态加载与初始化逻辑
    snapshot = _app.get_state(config)
    current_input = None
    
    if not snapshot.values:
        # --- [New Task] ---
        # 如果没有历史状态，视为新任务启动
        project_state = ProjectState(
            task_id=f"TASK-{thread_id[-4:] if len(thread_id)>=4 else random.randint(1000,9999)}",
            user_input=user_input,
            full_chat_history=[{"role": "user", "parts": [{"text": user_input}]}]
        )
        current_input = {"project_state": project_state}
        yield {"event_type": "status", "data": f"🚀 Task Initialized: {project_state.task_id}"}
        
    else:
        # --- [Resume / Feedback] ---
        # 如果存在状态，检查是否处于中断点 (HITL)
        if snapshot.next:
            yield {"event_type": "status", "data": "🔄 Resuming from pause..."}
            
            # 如果用户提供了输入，将其视为反馈注入
            if user_input:
                current_ps = snapshot.values.get('project_state')
                if current_ps:
                    # 将用户输入更新到反馈队列
                    current_ps.user_feedback_queue = f"User Feedback: {user_input}"
                    _app.update_state(config, {"project_state": current_ps})
                    yield {"event_type": "feedback_received", "data": "Feedback injected into state."}
            
            # Resume 执行 (Input 设为 None)
            current_input = None
        else:
            # 任务已完成但用户又发了消息，可能需要重置或作为新任务
            # 这里简单处理：提示已完成
            yield {"event_type": "warning", "data": "Task already completed."}
            return

    # 2. 执行流式循环
    try:
        # 使用 astream 捕获每一步的输出
        async for event in _app.astream(current_input, config=config):
            for node_name, node_state in event.items():
                project_state = node_state.get('project_state')
                
                # 构造节点完成事件
                event_payload = {
                    "node": node_name,
                    "router_decision": project_state.router_decision if project_state else "unknown",
                    "next_step": project_state.next_step if project_state else None
                }
                
                yield {
                    "event_type": "node_finished",
                    "data": event_payload
                }
                
                # 如果有 Coding Crew 的输出
                if node_name == "coding_crew" and project_state and project_state.code_blocks:
                    # 获取最新的代码块 (简化逻辑)
                    latest_code = list(project_state.code_blocks.values())[-1]
                    yield {"event_type": "artifact_code", "data": latest_code[:200] + "..."}

                # 如果有最终报告 (Data/Content Crew)
                if project_state and project_state.final_report and node_name in ["data_crew", "content_crew"]:
                     yield {
                         "event_type": "final_report",
                         "data": project_state.final_report
                     }

        # 3. 检查最终状态 (判断是完成还是暂停)
        final_snapshot = _app.get_state(config)
        if final_snapshot.next:
            # 遇到 interrupt_before，暂停
            yield {
                "event_type": "interrupt", 
                "data": {
                    "msg": "Workflow paused for human review.",
                    "next_node": final_snapshot.next
                }
            }
        else:
            # 流程自然结束
            yield {"event_type": "finish", "data": "✅ Workflow Completed."}

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"event_type": "error", "data": str(e)}
