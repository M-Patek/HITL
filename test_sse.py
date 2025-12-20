import asyncio
import json
import sys
import httpx

# API 基础地址
API_BASE = "http://127.0.0.1:8000"

async def run_test():
    """
    模拟完整的前端交互流程: Start -> Stream -> Receive Events
    """
    # 1. 准备任务负载
    initial_payload = {
        "user_input": "请帮我写一个 Python 贪吃蛇游戏，并分析其算法复杂度。",
        "thread_id": "cli_test_thread_001" # 可选
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # === Step 1: 启动任务 ===
        print(f"🚀 [Step 1] Initializing Task at {API_BASE}/api/start_task...")
        print(f"   Payload: {json.dumps(initial_payload, ensure_ascii=False)}")
        
        try:
            resp = await client.post(f"{API_BASE}/api/start_task", json=initial_payload)
            resp.raise_for_status()
            
            data = resp.json()
            task_id = data["task_id"]
            print(f"✅ Task Started! Task ID: {task_id}")
            
        except httpx.HTTPStatusError as e:
            print(f"❌ Failed to start task: {e.response.text}")
            return
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return

        # === Step 2: 监听 SSE 流 ===
        stream_url = f"{API_BASE}/api/stream/{task_id}"
        print(f"\n🔌 [Step 2] Connecting to Event Stream: {stream_url}")
        print("--- Stream Listening (Press Ctrl+C to stop) ---")

        try:
            # timeout=None 保持长连接
            async with client.stream("GET", stream_url, timeout=None) as response:
                if response.status_code != 200:
                    print(f"❌ Stream Connection Failed: {response.status_code}")
                    return

                # 模拟 EventSource 解析逻辑
                current_event_type = None
                
                async for line in response.aiter_lines():
                    if not line:
                        # 空行代表一个 Event 块结束 (或心跳)
                        current_event_type = None
                        continue

                    # 打印原始数据帧，方便调试
                    # print(f"[RAW] {line}") 

                    # 解析 SSE 协议
                    if line.startswith("event: "):
                        current_event_type = line[7:].strip()
                    
                    elif line.startswith("data: "):
                        data_str = line[6:].strip()
                        
                        # 处理结束信号
                        if data_str == "end":
                            print("\n🏁 [Finish] Server signaled end of stream.")
                            return

                        # 尝试解析 JSON 数据
                        try:
                            data_json = json.loads(data_str)
                            # 格式化输出
                            prefix = f"[{current_event_type.upper()}]" if current_event_type else "[DATA]"
                            print(f"{prefix} {json.dumps(data_json, ensure_ascii=False)}")
                        except:
                            print(f"[DATA] {data_str}")

        except asyncio.CancelledError:
            print("\n🛑 Task cancelled.")
        except Exception as e:
            print(f"\n💥 Stream Error: {e}")
        finally:
            print("--- Disconnected ---")

if __name__ == "__main__":
    try:
        # 检查依赖
        import httpx
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_test())
    except ImportError:
        print("❌ Missing dependency 'httpx'. Please run: pip install httpx")
    except KeyboardInterrupt:
        print("\n👋 Bye!")
