from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import time
import asyncio
import json
import logging
from collections import defaultdict

from config.keys import GEMINI_API_KEYS, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from core.api_models import TaskRequest  # [Fix] Import unified model
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from workflow.graph import build_agent_workflow
from langgraph.checkpoint.memory import MemorySaver
from core.models import ProjectState

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_server")

# 初始化 App
app = FastAPI(title="Gemini HITL API", version="2.0.0")

# --- 1. CORS 配置 (允许跨域) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化全局组件
checkpointer = MemorySaver()
rotator = GeminiKeyRotator(GEMINI_API_KEYS[0], GEMINI_API_KEYS[0]) # Assuming keys provided in env
memory = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
search = GoogleSearchTool()

# 构建工作流图
workflow_app = build_agent_workflow(rotator, memory, search, checkpointer=checkpointer)

# --- 事件流管理器 (核心升级) ---
class EventStreamManager:
    def __init__(self):
        # 存储每个任务的事件队列: task_id -> asyncio.Queue
        self.active_streams: Dict[str, asyncio.Queue] = {}

    async def create_stream(self, task_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.active_streams[task_id] = queue
        return queue

    async def push_event(self, task_id: str, event_type: str, data: Any):
        if task_id in self.active_streams:
            # 构造 SSE 格式的数据包
            payload = {"type": event_type, "timestamp": time.strftime("%H:%M:%S"), "data": data}
            await self.active_streams[task_id].put(payload)

    async def close_stream(self, task_id: str):
        if task_id in self.active_streams:
            await self.active_streams[task_id].put(None) # 发送结束信号
            del self.active_streams[task_id]

stream_manager = EventStreamManager()

class InterventionRequest(BaseModel):
    task_id: str
    command: str

# --- Helper Functions ---

async def run_workflow_background(task_id: str, initial_input: Dict, config: Dict):
    """
    后台运行工作流，并将事件实时推送到 SSE 队列
    [Fix] Added cancellation handling
    """
    thread_id = config["configurable"]["thread_id"]
    logger.info(f"🚀 [Background] Workflow started for: {task_id}")
    
    await stream_manager.push_event(task_id, "macro_log", {
        "agent": "System", "message": "Workflow Initialized.", "run_id": None
    })

    try:
        # stream_mode="values" 获取状态快照
        async for event in workflow_app.astream(initial_input, config=config, stream_mode="values"):
            if 'project_state' in event:
                ps: ProjectState = event['project_state']
                
                # 1. 捕获宏观决策 (Macro Log)
                if ps.next_step:
                    agent_name = ps.next_step.get('agent_name', 'Unknown')
                    instruction = ps.next_step.get('instruction', '')
                    run_id = ps.next_step.get('run_id')
                    
                    await stream_manager.push_event(task_id, "macro_log", {
                        "agent": agent_name,
                        "message": f"Executing: {instruction[:50]}...",
                        "run_id": run_id
                    })

                # 2. 捕获产出物 (Artifacts)
                if ps.artifacts.get("images"):
                    for img in ps.artifacts["images"][-1:]: 
                         await stream_manager.push_event(task_id, "artifact", {
                             "type": "image", 
                             "label": img.get('filename', 'output.png'), 
                             "content": img.get('data') 
                         })

                # 3. 模拟捕获微观日志 (Micro Log)
                if ps.next_step and ps.next_step.get('run_id'):
                     await stream_manager.push_event(task_id, "micro_log_signal", {
                         "run_id": ps.next_step.get('run_id'),
                         "status": "processing"
                     })

    except asyncio.CancelledError:
        logger.warning(f"⚠️ Workflow cancelled: {task_id}")
        await stream_manager.push_event(task_id, "error", "Task was cancelled by server shutdown.")
        # Do not re-raise if we want to suppress stack trace in server logs, 
        # or re-raise to let FastAPI background task handler know. 
        # Usually cleaner to just log and exit.

    except Exception as e:
        logger.error(f"💥 Workflow failed: {e}", exc_info=True)
        await stream_manager.push_event(task_id, "error", str(e))
    finally:
        logger.info(f"🏁 Workflow finished: {task_id}")
        await stream_manager.push_event(task_id, "macro_log", {
            "agent": "System", "message": "Task Completed/Stopped.", "run_id": None
        })
        await stream_manager.close_stream(task_id)

# --- Endpoints ---

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Gemini Commander API"}

@app.post("/api/start_task")
async def start_task(req: TaskRequest, background_tasks: BackgroundTasks):
    """启动任务并准备流"""
    # [Fix] Use req.user_input instead of req.task
    if not req.user_input:
        raise HTTPException(status_code=400, detail="Task required (user_input)")

    task_id = f"task_{int(time.time())}"
    # Use provided thread_id or generate new one
    thread_id = req.thread_id if req.thread_id else f"thread_{task_id}"
    
    # 初始化 State
    user_parts = [{"text": req.user_input}]
    ps = ProjectState(
        task_id=task_id,
        user_input=req.user_input,
        full_chat_history=[{"role": "user", "parts": user_parts}]
    )
    
    # 构造 AgentGraphState
    initial_input = {"project_state": ps}
    config = {"configurable": {"thread_id": thread_id}}
    
    # 初始化事件流队列
    await stream_manager.create_stream(task_id)
    
    # 启动后台任务
    background_tasks.add_task(run_workflow_background, task_id, initial_input, config)
    
    return {"status": "started", "task_id": task_id, "thread_id": thread_id}

@app.get("/api/stream/{task_id}")
async def stream_events(task_id: str, request: Request):
    """
    SSE 实时事件流接口
    前端使用 EventSource 连接此接口
    """
    async def event_generator():
        queue = stream_manager.active_streams.get(task_id)
        if not queue:
            # 如果没有队列，尝试创建一个新的或者报错
            # 这里简单处理：如果任务不存在，发送结束并退出
            yield f"event: error\ndata: Task not found or finished\n\n"
            return

        while True:
            # 检查客户端是否断开连接
            if await request.is_disconnected():
                break
                
            # 获取事件
            payload = await queue.get()
            if payload is None: # 结束信号
                yield f"event: finish\ndata: end\n\n"
                break
            
            # SSE 格式: event: type \n data: json \n\n
            yield f"event: {payload['type']}\ndata: {json.dumps(payload['data'])}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/intervention")
async def inject_intervention(req: InterventionRequest):
    """
    HITL: 强行注入用户指令 (神谕)
    """
    # 找到对应的 thread_id (这里简化假设是一一对应，实际可能需要查找)
    thread_id = f"thread_{req.task_id}"
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # 获取当前状态
        state = workflow_app.get_state(config)
        if not state.values:
             raise HTTPException(status_code=404, detail="Task state not found")
             
        ps: ProjectState = state.values['project_state']
        
        # 注入高优先级反馈
        ps.user_feedback_queue = f"⚠️ [INTERVENTION]: {req.command}"
        
        # 立即更新状态
        workflow_app.update_state(config, {"project_state": ps})
        
        await stream_manager.push_event(req.task_id, "macro_log", {
            "agent": "Human (HITL)", 
            "message": f"Intervention injected: {req.command}",
            "run_id": None
        })
        
        return {"status": "injected", "message": "God mode command received"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 挂载静态文件
app.mount("/", StaticFiles(directory="static", html=True), name="static")
