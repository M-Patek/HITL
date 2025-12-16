import json
import asyncio
import os
from dotenv import load_dotenv

# [Fix] 1. 在导入其他模块之前，优先加载环境变量
# 这样能确保 config.keys 导入时能读取到 .env 中的值
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# 导入核心业务逻辑
# 注意：workflow.engine 内部会初始化 GeminiKeyRotator，所以必须在 load_dotenv 之后导入
from core.api_models import TaskRequest
from workflow.engine import run_workflow

app = FastAPI(title="Gemini Agent System API")

# 2. 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/stream_task")
async def stream_task(request: TaskRequest):
    """
    SSE 流式接口: 接收用户任务，实时推送 Agent 执行过程。
    """
    
    async def event_generator():
        workflow_stream = run_workflow(
            user_input=request.user_input, 
            thread_id=request.thread_id
        )

        try:
            async for event_type, data in workflow_stream:
                if await app.router.is_disconnected(request):
                    print("⚠️ Client disconnected, stopping workflow.")
                    break
                
                yield {
                    "event": event_type,
                    "data": json.dumps(data, ensure_ascii=False)
                }
                await asyncio.sleep(0.01)

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting API Server on http://0.0.0.0:8000")
    print("📱 Frontend available at http://0.0.0.0:8000/static/index.html")
    uvicorn.run(app, host="0.0.0.0", port=8000)
