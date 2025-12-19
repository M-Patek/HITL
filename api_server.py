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

from core.logger_setup import setup_logging, trace_id_ctx
from core.api_models import TaskRequest, FeedbackRequest
from workflow.engine import run_workflow, GLOBAL_CHECKPOINTER, _rotator, _memory_tool

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

@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())
    token = trace_id_ctx.set(req_id)
    try:
        logger.info("request_started", extra={"extra_data": {
            "path": request.url.path,
            "method": request.method
        }})
        response = await call_next(request)
        response.headers["X-Trace-ID"] = req_id
        return response
    finally:
        trace_id_ctx.reset(token)

@app.get("/system/status")
async def get_system_status():
    gateway_status = _rotator.check_gateway_health()
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
    """
    [Phase 4] Supports parallel heartbeat streaming via SSE
    """
    async def event_generator():
        workflow_stream = run_workflow(
            user_input=body.user_input, 
            thread_id=body.thread_id
        )

        try:
            async for event_data in workflow_stream:
                if await request.is_disconnected():
                    logger.info("client_disconnected")
                    break
                
                # 直接序列化 workflow 产生的所有事件 (包括 heartbeats)
                yield {
                    "event": event_data["event_type"],
                    "data": json.dumps(event_data["data"], ensure_ascii=False)
                }
                # 动态调整频率：如果是 heartbeat，间隔可以更短；如果是 heavy artifact，可以稍长
                # 这里保持统一心跳节奏
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
