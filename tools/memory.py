import os
import logging
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
    """
    def __init__(self, api_key: str, environment: str, index_name: str):
        self.enabled = bool(api_key and index_name and Pinecone)
        if self.enabled:
            self.pc = Pinecone(api_key=api_key)
            self.index = self.pc.Index(index_name)
        else:
            logger.warning("Pinecone not configured. Memory & Caching disabled.")

    def _get_embedding(self, text: str) -> List[float]:
        """获取文本嵌入 (Mock or Real)"""
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

    def check_semantic_cache(self, query: str, threshold: float = 0.95) -> Optional[str]:
        """
        [Phase 3] 语义缓存命中检查
        在调用 LLM 之前，先查库。如果发现极高相似度的问题，直接返回历史答案。
        """
        if not self.enabled: return None

        try:
            vector = self._get_embedding(query)
            if not vector: return None

            # 查询 Cache Namespace (假设我们将 Cache 存在专门的 namespace 或 metadata标记中)
            # 这里为了简单，直接查全局，通过 metadata.type='cache_entry' 过滤
            response = self.index.query(
                vector=vector,
                top_k=1,
                include_metadata=True,
                filter={"type": "cache_entry"} 
            )

            if response and response.matches:
                match = response.matches[0]
                if match.score >= threshold:
                    logger.info(f"⚡️ [Cache Hit] Query: '{query[:20]}...' (Score: {match.score:.4f})")
                    return match.metadata.get("response_text")
        
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            
        return None

    def store_cache(self, query: str, response: str):
        """将 LLM 的问答对存入缓存"""
        if not self.enabled: return
        try:
            vector = self._get_embedding(query)
            if vector:
                self.index.upsert(vectors=[{
                    "id": f"cache-{hash(query)}",
                    "values": vector,
                    "metadata": {
                        "type": "cache_entry",
                        "query_text": query,
                        "response_text": response
                    }
                }])
        except Exception as e:
            logger.warning(f"Failed to store cache: {e}")
