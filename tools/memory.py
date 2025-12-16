from typing import List, Optional
from google import genai
# 使用 try-import 模式以防止缺少依赖时直接崩溃
try:
    from pinecone import Pinecone, ServerlessSpec, Index
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

from config.keys import EMBEDDING_MODEL

# =======================================================
# VectorMemoryTool (RAG)
# =======================================================

class VectorMemoryTool:
    """
    基于 Pinecone 和 Gemini Embedding 的向量记忆库。
    """
    def __init__(self, api_key: str, environment: str, index_name: str):
        self.is_active = False
        self.index: Optional[Any] = None
        self.embedding_model = EMBEDDING_MODEL

        # 检查是否应该激活 RAG
        should_activate = (
            PINECONE_AVAILABLE 
            and api_key 
            and api_key != "YOUR_PINECONE_API_KEY"
        )

        if should_activate:
            print(f"🌲 [Memory] Initializing Pinecone index: {index_name}...")
            try:
                self.pc = Pinecone(api_key=api_key)
                
                # 检查并创建索引
                existing_indexes = [i.name for i in self.pc.list_indexes()]
                if index_name not in existing_indexes:
                    print(f"🌲 [Memory] Creating new index '{index_name}'...")
                    self.pc.create_index(
                        name=index_name,
                        dimension=768, 
                        metric='cosine',
                        spec=ServerlessSpec(cloud='aws', region='us-east-1')
                    )
                
                self.index = self.pc.Index(index_name)
                self.embed_client = genai.Client() # 假设已配置 Env
                self.is_active = True
                print("✅ [Memory] RAG System Activated.")
                
            except Exception as e:
                print(f"⚠️ [Memory] Initialization Failed: {e}. Switching to Mock Mode.")
        else:
            print("⚠️ [Memory] Running in Mock Mode (Missing Keys or Dependencies).")

    def _get_embedding(self, text: str) -> List[float]:
        """获取文本向量"""
        if not self.is_active: return [0.0] * 768
        try:
            res = self.embed_client.models.embed_content(
                model=self.embedding_model,
                content=text
            )
            return res.embeddings[0].values
        except Exception as e:
            print(f"❌ Embedding Error: {e}")
            return []

    def store_output(self, task_id: str, content: str, agent_role: str):
        """存储记忆"""
        if not self.is_active or not content: return
        
        try:
            vector = self._get_embedding(content)
            if not vector: return

            vector_id = f"{task_id}-{agent_role}-{hash(content)}"
            self.index.upsert(vectors=[{
                "id": vector_id,
                "values": vector,
                "metadata": {
                    "task_id": task_id,
                    "agent": agent_role,
                    "text": content[:1000] # 截断存储
                }
            }])
            print(f"💾 [Memory] Stored {agent_role}'s output.")
        except Exception as e:
            print(f"❌ Store Error: {e}")

    def delete_task_memory(self, task_id: str):
        """清理记忆"""
        if self.is_active:
            try:
                # 注意：Pinecone Delete by Metadata 并非所有层级都支持，视具体版本而定
                # 这里仅作演示
                print(f"🗑️ [Memory] Deleting memory for task {task_id}...")
            except Exception:
                pass
