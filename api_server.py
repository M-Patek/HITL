import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from workflow.engine import SwarmEngine
from core.models import UserInput, TaskStatus
from core.rotator import GeminiKeyRotator
from tools.memory import VectorMemoryTool
from tools.search import GoogleSearchTool
from config.keys import (
    GATEWAY_API_BASE, 
    GATEWAY_SECRET,
    PINECONE_API_KEY,
    PINECONE_ENVIRONMENT,
    VECTOR_INDEX_NAME
)

# --- 初始化核心组件 ---

# 1. Rotator (LLM Gateway)
_rotator = GeminiKeyRotator(base_url=GATEWAY_API_BASE, api_key=GATEWAY_SECRET)

# 2. Tools
_memory_tool = VectorMemoryTool(
    api_key=PINECONE_API_KEY,
    environment=PINECONE_ENVIRONMENT,
    index_name=VECTOR_INDEX_NAME
)
_search_tool = GoogleSearchTool()

# 3. Swarm Engine
engine = SwarmEngine(
    rotator=_rotator,
    memory_tool=_memory_tool,
    search_tool=_search_tool
)

# --- FastAPI App ---
app = FastAPI(
    title="Gemini Swarm HITL API",
    description="Human-in-the-Loop Orchestration Backend",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---

@app.get("/system/status")
async def health_check():
    """检查系统组件健康状态"""
    # 修复：_memory_tool 使用 .enabled 而不是 .is_active
    memory_status = "active" if _memory_tool.enabled else "mock_mode"
    
    # 修复：Rotator 现在有了 check_gateway_health 方法 (在 core/rotator.py 中修复)
    llm_status = _rotator.check_gateway_health()
    
    return {
        "status": "online",
        "components": {
            "llm_gateway": llm_status,
            "memory_db": memory_status,
            "engine": "ready"
        }
    }

@app.post("/task/create")
async def create_task(input_data: UserInput):
    """创建新任务"""
    try:
        task_id = engine.create_task(input_data.prompt)
        return {"task_id": task_id, "status": "initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/task/{task_id}/stream")
async def stream_task_events(task_id: str):
    """SSE 端点：流式传输任务进度"""
    return StreamingResponse(
        engine.stream_task_events(task_id),
        media_type="text/event-stream"
    )

@app.post("/task/{task_id}/feedback")
async def submit_feedback(task_id: str, feedback: dict):
    """提交用户反馈 (HITL)"""
    content = feedback.get("content")
    if not content:
        raise HTTPException(status_code=400, detail="Feedback content required")
    
    success = engine.submit_user_feedback(task_id, content)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return {"status": "feedback_received"}

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
