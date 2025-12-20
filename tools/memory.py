import os
import logging
import asyncio
from functools import partial
from typing import List, Dict, Any, Optional
# 假设使用 google.generativeai 或其他方式获取 embedding
import google.generativeai as genai 

try:
    from pinecone import Pinecone
except ImportError:
    Pinecone = None

logger = logging.getLogger("Tools-Memory")

class VectorMemoryTool:
    """
    [Protocol Phase 3 Enhanced]
    支持语义缓存 (Semantic Caching) 的向量记忆工具。
    已全面异步化 (Async I/O non-blocking)。
    """
    def __init__(self, api_key: str, environment: str, index_name: str):
        # 检查是否具备启用条件
        self.enabled = bool(api_key and index_name and Pinecone)
        self.index = None
        if self.enabled:
            try:
                self.pc = Pinecone(api_key=api_key)
                self.index = self.pc.Index(index_name)
            except Exception as e:
                logger.error(f"Pinecone init failed: {e}")
                self.enabled = False
        else:
            logger.warning("Pinecone not configured. Memory & Caching disabled.")

    def _get_embedding_sync(self, text: str) -> List[float]:
        """同步获取嵌入 (内部 Helper)"""
        if not text: return []
        try:
            # 这里的 model 需与您的 Pinecone index 维度一致 (e.g., 768)
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_query"
            )
            return result['embedding']
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return []

    async def _get_embedding(self, text: str) -> List[float]:
        """异步获取嵌入 (Non-blocking wrapper)"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_embedding_sync, text)

    async def check_semantic_cache(self, query: str, threshold: float = 0.95) -> Optional[str]:
        """
        [Phase 3] 语义缓存命中检查 (Async)
        """
        if not self.enabled or not self.index: return None

        try:
            # 1. 获取向量 (Async)
            vector = await self._get_embedding(query)
            if not vector: return None

            # 2. 查询 Pinecone (Run in Executor)
            loop = asyncio.get_running_loop()
            
            # 定义同步查询函数
            def _query_pinecone():
                return self.index.query(
                    vector=vector,
                    top_k=1,
                    include_metadata=True,
                    filter={"type": "cache_entry"} 
                )
            
            response = await loop.run_in_executor(None, _query_pinecone)

            if response and response.matches:
                match = response.matches[0]
                if match.score >= threshold:
                    logger.info(f"⚡️ [Cache Hit] Query: '{query[:20]}...' (Score: {match.score:.4f})")
                    return match.metadata.get("response_text")
        
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            
        return None

    async def store_cache(self, query: str, response: str):
        """将 LLM 的问答对存入缓存 (Async)"""
        if not self.enabled or not self.index: return
        try:
            vector = await self._get_embedding(query)
            if vector:
                loop = asyncio.get_running_loop()
                def _upsert_cache():
                    self.index.upsert(vectors=[{
                        "id": f"cache-{hash(query)}",
                        "values": vector,
                        "metadata": {
                            "type": "cache_entry",
                            "query_text": query,
                            "response_text": response
                        }
                    }])
                await loop.run_in_executor(None, _upsert_cache)
        except Exception as e:
            logger.warning(f"Failed to store cache: {e}")

    async def store_output(self, task_id: str, content: str, agent_role: str):
        """
        存储 Agent 的产出到长期记忆中 (Async)
        """
        if not self.enabled or not self.index: 
            logger.info(f"💾 [Memory Mock] Storing output from {agent_role} (Pinecone Disabled)")
            return

        try:
            vector = await self._get_embedding(content)
            if vector:
                loop = asyncio.get_running_loop()
                def _upsert_memory():
                    self.index.upsert(vectors=[{
                        "id": f"mem-{task_id}-{agent_role}-{hash(content)}",
                        "values": vector,
                        "metadata": {
                            "type": "agent_output",
                            "task_id": task_id,
                            "agent": agent_role,
                            "content_snippet": content[:500]
                        }
                    }])
                await loop.run_in_executor(None, _upsert_memory)
                logger.info(f"💾 [Memory] Saved output from {agent_role}")
        except Exception as e:
            logger.error(f"Failed to store output: {e}")
