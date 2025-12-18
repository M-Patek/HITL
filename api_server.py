import json
import asyncio
import os
import uuid
import logging
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# [New] 引入日志基建
from core.logger_setup import setup_logging, trace_id_ctx
from core.api_models import TaskRequest, FeedbackRequest
from workflow.engine import run_workflow, GLOBAL_CHECKPOINTER, _rotator, _memory_tool

# 1. 初始化 Brain 日志
setup_logging("SWARM-Brain")
logger = logging.getLogger("API")

app = FastAPI(title="Gemini Agent System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# [New] 全链路追踪中间件 (Genesis)
@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    # 生成唯一 ID (这是全链路的起源)
    req_id = str(uuid.uuid4())
    
    # [关键] 放入上下文，之后的 Rotator 代码都能自动获取
    token = trace_id_ctx.set(req_id)
    
    try:
        logger.info("request_started", extra={"extra_data": {
            "path": request.url.path,
            "method": request.method,
            "client_ip": request.client.host
        }})
        
        response = await call_next(request)
        
        # 返回 ID 给前端 Debug
        response.headers["X-Trace-ID"] = req_id
        return response
    finally:
        trace_id_ctx.reset(token)

# [New] Brain 系统自检接口
@app.get("/system/status")
async def get_system_status():
    """
    [接口功能]: 汇报 Brain 自身状态，并展示与 Gateway 和 Pinecone 的连接情况。
    """
    # 1. 检查 Gateway 链路 (调用 Rotator 新增的方法)
    gateway_status = _rotator.check_gateway_health()
    
    # 2. 检查 记忆库 (Pinecone) 状态
    memory_status = "active" if _memory_tool.is_active else "mock_mode"
    
    return {
        "service": "SWARM-Brain",
        "role": "Orchestrator",
        "health": "ok",
        "dependencies": {
            "gateway": gateway_status,
            "memory_storage": memory_status
        }
    }

@app.post("/stream_task")
async def stream_task(body: TaskRequest, request: Request):
    async def event_generator():
        workflow_stream = run_workflow(
            user_input=body.user_input, 
            thread_id=body.thread_id
        )

        try:
            async for event_type, data in workflow_stream:
                if await request.is_disconnected():
                    logger.info("client_disconnected")
                    break
                
                yield {
                    "event": event_type,
                    "data": json.dumps(data, ensure_ascii=False)
                }
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error("stream_error", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())

@app.post("/feedback")
async def submit_feedback(body: FeedbackRequest):
    thread_id = body.thread_id
    if not thread_id:
        raise HTTPException(status_code=400, detail="Thread ID is required")
        
    logger.info(f"feedback_received", extra={"extra_data": {"thread": thread_id}})
    return {"status": "received", "message": "Feedback queued."}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting API Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
