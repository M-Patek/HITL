from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import time
import asyncio
import logging

from config.keys import GEMINI_API_KEYS, PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from workflow.graph import build_agent_workflow
from langgraph.checkpoint.memory import MemorySaver
from core.models import ProjectState  # Added Import

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_server")

# 初始化 App
app = FastAPI(title="Gemini HITL API", version="1.0.0")

# --- 1. CORS 配置 (允许跨域) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化全局状态 (模拟单例)
checkpointer = MemorySaver()
rotator = GeminiKeyRotator(GEMINI_API_KEYS)
memory = VectorMemoryTool(PINECONE_API_KEY, PINECONE_ENVIRONMENT, VECTOR_INDEX_NAME)
search = GoogleSearchTool()

# 构建图 (复用逻辑)
workflow_app = build_agent_workflow(rotator, memory, search, checkpointer=checkpointer)

# --- API Models ---

class TaskRequest(BaseModel):
    task: str

class FeedbackRequest(BaseModel):
    feedback: str
    thread_id: str

# --- Helper Functions ---

async def run_workflow_background(app_workflow, initial_input: Dict, config: Dict):
    """后台运行工作流的任务函数"""
    thread_id = config["configurable"]["thread_id"]
    logger.info(f"🚀 [Background] Workflow started for thread: {thread_id}")
    try:
        # stream_mode="values" 确保状态被持久化到 checkpointer
        async for event in app_workflow.astream(initial_input, config=config, stream_mode="values"):
            if 'project_state' in event:
                ps = event['project_state']
                if ps.next_step:
                    logger.info(f"   🔄 [Running] {ps.next_step.get('agent_name')} -> {ps.next_step.get('instruction')[:30]}...")
    except Exception as e:
        logger.error(f"💥 [Background] Workflow failed: {e}", exc_info=True)
    finally:
        logger.info(f"🏁 [Background] Workflow finished for thread: {thread_id}")

# --- Endpoints ---

@app.get("/health")
async def health_check():
    """系统监控健康检查"""
    return {
        "status": "healthy", 
        "uptime": time.time(),
        "service": "Gemini HITL API"
    }

@app.post("/api/start_task")
async def start_task(req: TaskRequest, background_tasks: BackgroundTasks):
    """
    启动新任务 (后台异步运行)
    """
    if not req.task:
        raise HTTPException(status_code=400, detail="Task description is required")

    # 生成 ID
    task_id = f"api_task_{int(time.time())}"
    thread_id = f"thread_{task_id}"
    
    # 初始化 State
    user_parts = [{"text": req.task}]
    project_state = ProjectState(
        task_id=task_id,
        user_input=req.task,
        full_chat_history=[{"role": "user", "parts": user_parts}]
    )
    
    initial_input = {"project_state": project_state}
    config = {"configurable": {"thread_id": thread_id}}
    
    # --- 2. 启动后台任务 ---
    # 使用 FastAPI 的 BackgroundTasks 将长时间运行的工作流放入后台
    background_tasks.add_task(run_workflow_background, workflow_app, initial_input, config)
    
    return {
        "status": "started", 
        "task_id": task_id, 
        "thread_id": thread_id,
        "message": "Workflow is running in background"
    }

@app.get("/api/state/{thread_id}")
async def get_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = workflow_app.get_state(config)
    if not state.values:
        return {"error": "No state found"}
    return state.values["project_state"]

@app.get("/api/runs/{run_id}/history")
async def get_subgraph_history(run_id: str):
    """
    [New] 获取子任务（Crew）的详细历史
    前端点击“展开详情”时调用此接口
    """
    config = {"configurable": {"thread_id": run_id}}
    
    # 我们需要访问子图的 checkpointer。由于 MemorySaver 是共享的，
    # 我们可以直接查询存储在其中的子图状态。
    # 注意：LangGraph 的 history 获取方式
    try:
        history = []
        async for state in workflow_app.aget_state_history(config):
            # 提取关键信息
            val = state.values
            step_info = {
                "created_at": state.created_at,
                "node": state.next, # 或者 active node
                "code": val.get("generated_code", ""),
                "feedback": val.get("review_feedback", ""),
                "stderr": val.get("execution_stderr", "")
            }
            history.append(step_info)
        
        return {"history": history, "run_id": run_id}
    except Exception as e:
        return {"error": str(e)}

# 挂载静态文件 (前端)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
