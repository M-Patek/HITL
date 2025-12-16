import json
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# 导入核心业务逻辑
from core.api_models import TaskRequest
from workflow.engine import run_workflow

app = FastAPI(title="Gemini Agent System API")

# 1. 配置 CORS (允许前端跨域访问)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议改为具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 挂载静态文件目录 (优化建议已采纳)
# 访问地址: http://localhost:8000/static/index.html
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/stream_task")
async def stream_task(request: TaskRequest):
    """
    SSE 流式接口: 接收用户任务，实时推送 Agent 执行过程。
    """
    
    async def event_generator():
        """
        将 workflow engine 的生成器转换为 sse-starlette 兼容的格式
        """
        # 获取工作流生成器
        workflow_stream = run_workflow(
            user_input=request.user_input, 
            thread_id=request.thread_id
        )

        try:
            async for event_type, data in workflow_stream:
                # 检查客户端是否断开连接 (sse-starlette 会处理大部分情况，但双保险更稳)
                if await app.router.is_disconnected(request):
                    print("⚠️ Client disconnected, stopping workflow.")
                    break
                
                # 构造 SSE 消息对象
                # sse-starlette 会自动处理 "event: ...\ndata: ...\n\n" 的格式
                yield {
                    "event": event_type,
                    "data": json.dumps(data, ensure_ascii=False)
                }
                
                # 极短的 yield 让渡，避免 event loop 阻塞
                await asyncio.sleep(0.01)

        except Exception as e:
            # 发生未捕获异常时，推送 error 事件给前端
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False)
            }

    # 使用 EventSourceResponse 包装生成器，自动处理 Content-Type 和 Connection 头
    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    # 启动命令: python api_server.py
    print("🚀 Starting API Server on http://0.0.0.0:8000")
    print("📱 Frontend available at http://0.0.0.0:8000/static/index.html")
    uvicorn.run(app, host="0.0.0.0", port=8000)
