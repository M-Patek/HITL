import os
import asyncio
from typing import Optional

# 尝试导入 Tavily，如果没装库则回退到 Mock
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False

class GoogleSearchTool:
    """
    真实搜索工具 (Powered by Tavily API).
    提供针对 AI 优化的实时网络搜索结果。
    """
    
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        self.client = None
        
        if TAVILY_AVAILABLE and self.api_key:
            print("🌐 [Search Tool] Tavily API Activated (Real-World Data).")
            self.client = TavilyClient(api_key=self.api_key)
        else:
            print("⚠️ [Search Tool] Tavily Key missing or lib not installed. Running in MOCK mode.")

    async def search(self, query: str) -> str:
        """
        执行搜索 (Async Wrapper)。
        """
        # 1. 如果没有客户端，走备用逻辑
        if not self.client:
            return self._fallback_search(query)

        print(f"🌐 [Search Tool] Searching via Tavily: {query[:40]}...")
        
        try:
            # Tavily 官方库是同步的，为了不阻塞 Brain 的主循环，我们在 Executor 中运行
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.client.search(
                    query, 
                    search_depth="basic", 
                    max_results=3,
                    include_answer=True # 让 Tavily 尝试直接回答
                )
            )
            
            # 2. 格式化结果供 LLM 阅读
            context = []
            
            # 如果有 Tavily 生成的直接回答，优先使用
            if response.get("answer"):
                 context.append(f"Direct Answer: {response['answer']}")
            
            # 遍历搜索结果
            for res in response.get("results", []):
                title = res.get('title', 'No Title')
                url = res.get('url', '#')
                content = res.get('content', '')[:1000] # 限制每条长度
                context.append(f"Source: {title}\nURL: {url}\nContent: {content}\n")
            
            final_result = "\n---\n".join(context)
            return final_result if final_result else "No results found."

        except Exception as e:
            print(f"⚠️ [Search Tool] API Error: {e}. Switching to Fallback.")
            return self._fallback_search(query)

    def _fallback_search(self, query: str) -> str:
        """
        备用 Mock 逻辑 (当 Tavily 不可用时)
        """
        q_lower = query.lower()
        prefix = "[Source: Fallback/Mock] "
        
        if "python" in q_lower or "code" in q_lower:
             return prefix + "Result: Python 3.12 was released with significant performance improvements. asyncio has new features."
        elif "data" in q_lower or "trend" in q_lower:
             return prefix + "Result: Global data market is growing by 20% YoY. AI adoption is the key driver."
        else:
             return prefix + f"Result: Simulated search result for '{query}'."
