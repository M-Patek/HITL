from typing import str

# =======================================================
# GoogleSearchTool
# =======================================================

class GoogleSearchTool:
    """
    外部搜索工具封装。
    目前处于模拟模式 (Mock Mode)。
    """
    
    def search(self, query: str) -> str:
        """
        执行搜索并返回摘要。
        """
        print(f"🌐 [Search Tool] Searching for: {query[:40]}...")
        
        # 模拟逻辑：根据关键词返回不同假数据
        q_lower = query.lower()
        
        if "python" in q_lower or "code" in q_lower:
             return "Result: Python 3.12 was released with significant performance improvements. asyncio has new features."
        elif "data" in q_lower or "trend" in q_lower:
             return "Result: Global data market is growing by 20% YoY. AI adoption is the key driver."
        elif "story" in q_lower or "write" in q_lower:
             return "Result: Hero's Journey is a common template for storytelling. Conflict drives the plot."
        else:
             return "Result: No specific data found, but general knowledge suggests this is a popular topic."
