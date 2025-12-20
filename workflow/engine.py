import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime

from langgraph.checkpoint.memory import MemorySaver

from config.keys import GATEWAY_API_BASE, GATEWAY_SECRET, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from core.models import ProjectState, TaskNode, TaskStatus, ArtifactVersion
from workflow.graph import build_agent_workflow
from core.logger_setup import node_id_ctx, trace_id_ctx, phase_ctx, token_usage_ctx

logger = logging.getLogger("Brain-Engine")
GLOBAL_CHECKPOINTER = MemorySaver()

_rotator = GeminiKeyRotator(GATEWAY_API_BASE, GATEWAY_SECRET)
_memory_tool = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
_search_tool = GoogleSearchTool()
_app = build_agent_workflow(_rotator, _memory_tool, _search_tool, checkpointer=GLOBAL_CHECKPOINTER)

def get_breadcrumbs(state: ProjectState) -> List[Dict[str, str]]:
    """
    [Phase 4 Upgrade] 面包屑导航适配并行分支
    """
    breadcrumbs = []
    current_id = state.active_node_id
    
    # 1. 检查是否处于并行执行状态 (通过 Vector Clock 判断)
    # 如果 vector_clock 中有多个非零项，且不仅只有 'main'，说明可能在并行
    active_branches = [k for k, v in state.vector_clock.items() if v > 0 and k != "main"]
    is_parallel = len(active_branches) > 0

    while current_id:
        node = state.node_map.get(current_id)
        if not node: break
        
        label = node.instruction[:30]
        
        breadcrumbs.append({
            "id": node.node_id,
            "label": label, 
            "level": node.level,
            "status": node.status,
            # [New] 带上时钟信息，前端可用于渲染甘特图
            "clock": state.vector_clock.copy() 
        })
        current_id = node.parent_id
        
    return list(reversed(breadcrumbs))

def validate_subtree_output(node: TaskNode) -> Dict[str, Any]:
    if node.status != TaskStatus.COMPLETED:
        return {"valid": True}
    if not node.semantic_summary:
        return {"valid": False, "msg": "Protocol Violation: Missing Summary"}
    # 放宽限制，聚合器的摘要可能较短
    if len(node.semantic_summary) < 5:
        return {"valid": False, "msg": "Protocol Violation: Summary too short"}
    return {"valid": True}

async def run_workflow(user_input: str, thread_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    if _app is None:
        yield {"event_type": "error", "data": "Workflow Engine not initialized."}
        return

    current_trace_id = trace_id_ctx.get()
    if not current_trace_id:
        current_trace_id = str(uuid.uuid4())
        trace_id_ctx.set(current_trace_id)

    config = {"configurable": {"thread_id": thread_id}}
    
    snapshot = _app.get_state(config)
    current_input = None
    
    if not snapshot.values:
        ps = ProjectState.init_from_task(user_input, f"T-{thread_id[-4:]}")
        # [Fix] Ensure State Injection aligns with AgentGraphState Schema
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
                    # [Fix] Update state using the nested 'project_state' key
                    _app.update_state(config, {"project_state": ps})
            current_input = None
        else:
            yield {"event_type": "warning", "data": "Task already completed."}
            return

    last_phase = None
    sent_images = set() 
    sent_code_hashes = set()
    
    # [Phase 4 New] 记录上一次的向量时钟，用于检测“心跳”
    last_vector_clock = {}

    try:
        async for event in _app.astream(current_input, config=config, stream_mode="values"):
            if 'project_state' not in event: continue
            ps: ProjectState = event['project_state']
            
            # [Phase 4 New] Heartbeat Check
            if ps.vector_clock != last_vector_clock:
                diff = {k: ps.vector_clock[k] for k in ps.vector_clock if ps.vector_clock.get(k) != last_vector_clock.get(k)}
                yield {
                    "event_type": "heartbeat",
                    "data": {
                        "clock_diff": diff,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                last_vector_clock = ps.vector_clock.copy()
            
            active_node = ps.get_active_node()
            if active_node:
                node_id_ctx.set(active_node.node_id)
                current_phase = active_node.stage_protocol.current_phase
                phase_ctx.set(current_phase)
                
                if current_phase != last_phase:
                    yield {
                        "event_type": "protocol_step_start",
                        "data": {
                            "phase": current_phase,
                            "node_id": active_node.node_id,
                            "timestamp": datetime.now().isoformat()
                        }
                    }
                    last_phase = current_phase

                if active_node.status == TaskStatus.COMPLETED:
                    validation = validate_subtree_output(active_node)
                    if not validation["valid"]:
                        yield {"event_type": "warning", "data": f"⚠️ {validation['msg']}"}

            if ps.last_error:
                yield {"event_type": "error", "data": ps.last_error}
                ps.last_error = None
                continue
            
            # Update Status
            # 如果是并行列表，展示为 "Coding+Researcher" 等形式
            agent_label = "SYSTEM"
            if ps.next_step:
                if isinstance(ps.next_step.get("parallel_agents"), list):
                    agent_label = "+".join([str(a)[:4].upper() for a in ps.next_step["parallel_agents"]])
                else:
                    agent_label = ps.next_step.get("agent_name", "Unknown")
            
            yield {
                "event_type": "update", 
                "data": {
                    "status": ps.router_decision, 
                    "agent": agent_label
                }
            }
            
            yield {"event_type": "tree_update", "data": get_breadcrumbs(ps)}
            
            # [Version Control] Code
            if ps.code_blocks:
                latest_agent = list(ps.code_blocks.keys())[-1]
                code_content = ps.code_blocks[latest_agent]
                code_hash = hash(code_content)
                
                if code_hash not in sent_code_hashes:
                    ver_count = len([x for x in ps.artifact_history if x.type == "code"]) + 1
                    version = ArtifactVersion(
                        trace_id=trace_id_ctx.get(),
                        node_id=ps.active_node_id,
                        # [Phase 4 New] 注入向量时钟
                        vector_clock=ps.vector_clock.copy(),
                        type="code",
                        content=code_content,
                        label=f"v{ver_count}"
                    )
                    ps.artifact_history.append(version)
                    yield {"event_type": "artifact_code", "data": version.model_dump()}
                    sent_code_hashes.add(code_hash)
            
            # [Version Control] Images
            if "images" in ps.artifacts:
                for img in ps.artifacts["images"]:
                    if img['filename'] not in sent_images:
                        ver_count = len([x for x in ps.artifact_history if x.type == "image"]) + 1
                        version = ArtifactVersion(
                            trace_id=trace_id_ctx.get(),
                            node_id=ps.active_node_id,
                            vector_clock=ps.vector_clock.copy(),
                            type="image",
                            content=img,
                            label=f"img-{ver_count}"
                        )
                        ps.artifact_history.append(version)
                        yield {"event_type": "artifact_image", "data": version.model_dump()}
                        sent_images.add(img['filename'])
            
            if ps.final_report:
                yield {"event_type": "final_report", "data": ps.final_report}

        final_snapshot = _app.get_state(config)
        if final_snapshot.next:
            yield {"event_type": "interrupt", "data": {"node": final_snapshot.next[0], "msg": "Paused for HITL."}}
        else:
            yield {"event_type": "finish", "data": "✅ All tasks completed."}

    except Exception as e:
        logger.error(f"💥 Engine Crash: {e}", exc_info=True)
        yield {"event_type": "error", "data": f"Engine Crash: {str(e)}"}
