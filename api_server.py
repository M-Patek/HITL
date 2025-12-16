import json
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from core.api_models import TaskRequest
from workflow.engine import workflow_stream_generator

# 加载环境变量
load_dotenv()

# 初始化 FastAPI 实例
app = FastAPI(
    title="Gemini Multi-Agent Swarm API",
    description="Backend API for HITL Multi-Agent System",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """根路径健康检查"""
    return {"status": "running", "service": "Gemini Agent Swarm API"}

@app.post("/stream_task")
async def stream_task(request: TaskRequest):
    """
    SSE (Server-Sent Events) 端点。
    接收任务请求，实时推送 Agent 工作流的执行状态和结果。
    """
    async def event_generator():
        # 如果未提供 thread_id，生成默认 ID
        thread_id = request.thread_id or "default_thread_1"
        
        # 调用核心引擎的生成器
        async for event in workflow_stream_generator(request.user_input, thread_id):
            # 获取内部事件类型和数据
            internal_type = event.get("event_type", "status")
            data = event.get("data")
            
            # --- 事件映射逻辑 ---
            # 根据 API 规范，将内部事件映射为前端约定的: update, result, error, end
            sse_event = "update" # 默认为更新状态
            
            if internal_type == "final_report":
                sse_event = "result" # 最终结果
            elif internal_type == "error":
                sse_event = "error"  # 错误
            elif internal_type == "finish":
                sse_event = "end"    # 流程结束
                
            # 序列化数据为 JSON 字符串
            try:
                # ensure_ascii=False 保证中文正常显示
                json_data = json.dumps(data, ensure_ascii=False)
            except Exception:
                json_data = str(data)
            
            # 构造 SSE 格式数据 (event: ... \n data: ... \n\n)
            yield f"event: {sse_event}\ndata: {json_data}\n\n"

    # 返回流式响应，Content-Type 必须为 text/event-stream
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    # 允许通过直接运行脚本启动服务 (开发模式)
    # 启动命令: python api_server.py
    uvicorn.run(app, host="0.0.0.0", port=8000)
