import json
import sys

# 尝试导入 httpx，如果不存在则提示安装
try:
    import httpx
except ImportError:
    print("❌ Missing dependency. Please run: pip install httpx")
    sys.exit(1)

# API 地址 (假设运行在本地默认端口)
API_URL = "http://127.0.0.1:8000/stream_task"

def test_sse_stream():
    """
    模拟客户端连接 SSE 接口并打印流式数据
    """
    # 构造测试请求
    payload = {
        "user_input": "请帮我写一个 Python 贪吃蛇游戏，并分析其算法复杂度。",
        "thread_id": "cli_test_thread_001"
    }
    
    print(f"🔌 Connecting to {API_URL}...")
    print(f"📤 Payload: {json.dumps(payload, ensure_ascii=False)}\n")
    print("--- Stream Started ---")

    try:
        #发起流式 POST 请求
        # timeout=None 禁用超时，因为 Agent 执行可能较慢
        with httpx.stream("POST", API_URL, json=payload, timeout=None) as response:
            
            if response.status_code != 200:
                print(f"❌ Connection Failed: Status {response.status_code}")
                print(f"Details: {response.read().decode()}")
                return

            # 逐行读取流数据
            for line in response.iter_lines():
                if not line:
                    continue  # 跳过心跳或空行
                
                # 打印原始 SSE 数据帧 (格式通常为 event: ... \n data: ...)
                # 这样可以直观看到是否是“一个个事件”蹦出来的
                print(f"[Stream] {line}")
                
                # 简单的解析展示
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        # 尝试格式化 JSON 以便阅读
                        data_json = json.loads(data_str)
                        # 如果是比较长的文本(如代码)，截断显示
                        # print(f"   👉 Content: {str(data_json)[:100]}...") 
                    except:
                        pass

    except httpx.ConnectError:
        print("\n❌ Could not connect to the server. Is api_server.py running?")
    except Exception as e:
        print(f"\n💥 Unexpected Error: {e}")
    finally:
        print("\n--- Stream Ended ---")

if __name__ == "__main__":
    test_sse_stream()
