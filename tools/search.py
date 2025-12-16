import random
from typing import Optional

# =======================================================
# GoogleSearchTool
# =======================================================

class GoogleSearchTool:
    """
    外部搜索工具封装。
    包含自动降级策略 (Fallback Strategy)。
    """
    
    def search(self, query: str) -> str:
        """
        执行搜索并返回摘要。
        具备容错机制：如果主 API 失败，自动降级到 Mock 数据。
        """
        print(f"🌐 [Search Tool] Searching for: {query[:40]}...")
        
        try:
            # 1. 尝试调用真实 API (Primary)
            # 在此处集成真实的 Google Search API 客户端
            # response = google_client.search(query)
            # return response
            
            # [模拟]：此处模拟真实 API 未配置或超时的情况
            raise TimeoutError("Google Search API timed out (Simulated)")

        except Exception as e:
            # 2. 捕获异常并执行降级 (Fallback)
            print(f"⚠️ [Search Tool] Primary API failed: {e}. Switching to Fallback Mode.")
            return self._fallback_search(query)

    def _fallback_search(self, query: str) -> str:
        """
        备用搜索逻辑 (Mock Data)。
        返回的数据会标记 source='fallback'。
        """
        q_lower = query.lower()
        prefix = "[Source: Fallback] "
        
        # 模拟逻辑：根据关键词返回不同假数据
        if "python" in q_lower or "code" in q_lower:
             return prefix + "Result: Python 3.12 was released with significant performance improvements. asyncio has new features."
        elif "data" in q_lower or "trend" in q_lower:
             return prefix + "Result: Global data market is growing by 20% YoY. AI adoption is the key driver."
        elif "story" in q_lower or "write" in q_lower:
             return prefix + "Result: Hero's Journey is a common template for storytelling. Conflict drives the plot."
        else:
             return prefix + "Result: No specific data found, but general knowledge suggests this is a popular topic."
