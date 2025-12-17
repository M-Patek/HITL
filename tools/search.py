import httpx
import asyncio
from typing import Optional

# =======================================================
# GoogleSearchTool (Async & Improved)
# =======================================================

class GoogleSearchTool:
    """
    外部搜索工具封装。
    包含自动降级策略 (Fallback Strategy)。
    [Update] 改为异步实现，防止阻塞 Agent 工作流。
    """
    
    async def search(self, query: str) -> str:
        """
        执行搜索并返回摘要 (Async)。
        """
        print(f"🌐 [Search Tool] Searching for: {query[:40]}...")
        
        try:
            # 模拟真实的异步 HTTP 请求
            # 在实际生产中，这里应替换为 SerpApi 或 Google Custom Search 的 API URL
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 示例：假装调用一个 API (此处仅为占位，实际会触发异常进入 fallback)
                # response = await client.get(f"https://api.example.com/search?q={query}")
                # response.raise_for_status()
                # return response.json()['snippet']
                
                # 模拟网络延迟
                await asyncio.sleep(0.5) 
                raise TimeoutError("Search API not configured (Simulated)")

        except Exception as e:
            print(f"⚠️ [Search Tool] Primary API failed: {e}. Switching to Fallback Mode.")
            return self._fallback_search(query)

    def _fallback_search(self, query: str) -> str:
        """
        备用搜索逻辑 (Mock Data)。
        """
        q_lower = query.lower()
        prefix = "[Source: Fallback] "
        
        if "python" in q_lower or "code" in q_lower:
             return prefix + "Result: Python 3.12 was released with significant performance improvements. asyncio has new features."
        elif "data" in q_lower or "trend" in q_lower:
             return prefix + "Result: Global data market is growing by 20% YoY. AI adoption is the key driver."
        elif "story" in q_lower or "write" in q_lower:
             return prefix + "Result: Hero's Journey is a common template for storytelling. Conflict drives the plot."
        else:
             return prefix + "Result: No specific data found, but general knowledge suggests this is a popular topic."
