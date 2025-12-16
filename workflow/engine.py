import random
import asyncio
import os
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
GLOBAL_CHECKPOINTER = MemorySaver()

# [Fix] 增加对 API Key 的检查，避免 Server 启动崩溃
if not GEMINI_API_KEYS:
    print("⚠️ WARNING: GEMINI_API_KEYS not found in environment variables.")
    print("⚠️ System will start but Workflow execution will fail until keys are provided in .env")
    _rotator = None 
else:
    _rotator = GeminiKeyRotator(GEMINI_API_KEYS)

_memory_tool = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
_search_tool = GoogleSearchTool()

# [Fix] 延迟构建 Graph，或者处理 _rotator 为 None 的情况
if _rotator:
    _app = build_agent_workflow(_rotator, _memory_tool, _search_tool, checkpointer=GLOBAL_CHECKPOINTER)
else:
    _app = None 

async def run_workflow(
    user_input: str,
    thread_id: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    工作流执行引擎的核心生成器。
    """
    
    # [Fix] 运行时检查 Graph 是否初始化成功
    if _app is None:
        yield {"event_type": "error", "data": "System Error: GEMINI_API_KEYS not configured in .env file."}
        return

    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. 状态加载与初始化逻辑
    snapshot = _app.get_state(config)
    current_input = None
    
    if not snapshot.values:
        # 新任务
        project_state = ProjectState(
            task_id=f"TASK-{thread_id[-4:] if len(thread_id)>=4 else random.randint(1000,9999)}",
            user_input=user_input,
            full_chat_history=[{"role": "user", "parts": [{"text": user_input}]}]
        )
        current_input = {"project_state": project_state}
        yield {"event_type": "status", "data": f"🚀 Task Initialized: {project_state.task_id}"}
        
    else:
        # 恢复或反馈
        if snapshot.next:
            yield {"event_type": "status", "data": "🔄 Resuming from pause..."}
            if user_input:
                current_ps = snapshot.values.get('project_state')
                if current_ps:
                    current_ps.user_feedback_queue = f"User Feedback: {user_input}"
                    _app.update_state(config, {"project_state": current_ps})
                    yield {"event_type": "feedback_received", "data": "Feedback injected into state."}
            current_input = None
        else:
            yield {"event_type": "warning", "data": "Task already completed."}
            return

    # 2. 执行流式循环
    try:
        async for event in _app.astream(current_input, config=config):
            for node_name, node_state in event.items():
                
                # ================= [Fix Start] =================
                # 策略: 尝试解包，如果解包失败或为空，则直接从 Checkpoint 获取最新状态
                # 这样可以兜底解决 LangGraph 版本差异导致的 tuple 问题
                
                # 1. 尝试解包 tuple (如果是嵌套元组)
                temp_state = node_state
                while isinstance(temp_state, tuple):
                    if len(temp_state) > 0:
                        temp_state = temp_state[0]
                    else:
                        break # 空元组，无法继续解包
                
                # 2. 检查有效性: 是否为包含 project_state 的字典
                if isinstance(temp_state, dict) and 'project_state' in temp_state:
                    node_state = temp_state
                else:
                    # 3. 兜底: 从内存快照读取最新状态
                    # 只要节点事件触发了，Checkpoint 里一定有最新数据
                    print(f"⚠️ [Engine] Node '{node_name}' output is weird ({type(node_state)}). Fetching latest state from Checkpoint...")
                    latest_snapshot = _app.get_state(config)
                    if latest_snapshot.values and 'project_state' in latest_snapshot.values:
                        node_state = latest_snapshot.values
                    else:
                        print(f"⚠️ [Engine] Failed to recover state for {node_name}. Skipping.")
                        continue
                # ================= [Fix End] =================

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
                
                # Artifact 推送
                if node_name == "coding_crew" and project_state and project_state.code_blocks:
                    latest_code = list(project_state.code_blocks.values())[-1]
                    yield {"event_type": "artifact_code", "data": latest_code[:200] + "..."}

                if project_state and project_state.final_report and node_name in ["data_crew", "content_crew"]:
                     yield {
                         "event_type": "final_report",
                         "data": project_state.final_report
                     }

        # 3. 检查最终状态
        final_snapshot = _app.get_state(config)
        if final_snapshot.next:
            yield {
                "event_type": "interrupt", 
                "data": {
                    "msg": "Workflow paused for human review.",
                    "next_node": final_snapshot.next
                }
            }
        else:
            yield {"event_type": "finish", "data": "✅ Workflow Completed."}

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"event_type": "error", "data": str(e)}
