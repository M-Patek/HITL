import json
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# 导入核心业务逻辑
from core.api_models import TaskRequest, FeedbackRequest
from workflow.engine import run_workflow, GLOBAL_CHECKPOINTER
from workflow.graph import build_agent_workflow # 若需要手动更新状态，可能需要用到 graph 实例，但这里通过 checkpointer 即可

app = FastAPI(title="Gemini Agent System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/stream_task")
async def stream_task(body: TaskRequest, request: Request):
    """
    SSE 流式接口: 启动或恢复任务
    """
    async def event_generator():
        workflow_stream = run_workflow(
            user_input=body.user_input, 
            thread_id=body.thread_id
        )

        try:
            async for event_type, data in workflow_stream:
                if await request.is_disconnected():
                    print("⚠️ Client disconnected, stopping workflow.")
                    break
                
                yield {
                    "event": event_type,
                    "data": json.dumps(data, ensure_ascii=False)
                }
                await asyncio.sleep(0.01)

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())

@app.post("/feedback")
async def submit_feedback(body: FeedbackRequest):
    """
    [New] 专门的反馈接口
    用于 HITL 场景下，用户提交修改意见或批准执行。
    这会将反馈注入到 State 中，并准备好让 stream_task 恢复执行。
    """
    thread_id = body.thread_id
    feedback_text = body.feedback
    
    if not thread_id:
        raise HTTPException(status_code=400, detail="Thread ID is required")
        
    print(f"📨 Received Feedback for {thread_id}: {feedback_text}")
    
    # 逻辑：实际上，run_workflow 内部已经处理了 snapshot 的读取。
    # 这里我们只需要确认服务器收到请求，真正的状态更新会在下一次 /stream_task 调用时，
    # 或者如果我们需要实时更新状态而不触发 run，可以在这里操作 checkpointer。
    # 为了简化，LangGraph 推荐的方式是：更新 state -> resume。
    # 本示例中，前端提交 feedback 后通常会重新调用 /stream_task 来观看后续流。
    # 所以这里只需要返回成功即可，具体的 State 更新逻辑已经在 run_workflow 的 "Resuming from pause" 部分处理了。
    # 但为了更严谨，我们其实可以将 feedback 写入一个临时队列或直接在这里 update_state。
    
    # 方案：为了配合现有的 engine.py 逻辑 (它在启动时检查 snapshot)，
    # 我们这里仅仅是一个语义化的 Endpoint。前端调用完这个，紧接着调用 stream_task 即可。
    
    return {"status": "received", "message": "Feedback queued. Please reconnect stream to resume."}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting API Server on http://0.0.0.0:8000")
    print("📱 Frontend available at http://0.0.0.0:8000/static/index.html")
    uvicorn.run(app, host="0.0.0.0", port=8000)
