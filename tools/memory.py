from typing import List
# 导入所有必要的 Pinecone 客户端
from pinecone import Pinecone, ServerlessSpec, PodSpec, Index
from google import genai
from config.keys import EMBEDDING_MODEL # 导入配置

# =======================================================
# VectorMemoryTool (模拟/准备 RAG 内存库)
# =======================================================

class VectorMemoryTool:
    """
    负责 Agent 产出内容的向量化存储和语义检索。
    此模块将集成 Pinecone 向量数据库。
    """
    def __init__(self, api_key: str, environment: str, index_name: str):
        # 检查是否配置了 API Key，以决定是否激活 RAG
        self.is_active = (api_key != "YOUR_PINECONE_API_KEY") and (api_key is not None)
        self.index_name = index_name
        self.index: Index = None
        self.embedding_model = EMBEDDING_MODEL

        if self.is_active:
             print(f"🌲 记忆库初始化：正在连接到 Pinecone 索引 {index_name}...")
             try:
                 # 实际代码会在此处初始化 Pinecone 客户端
                 self.pc = Pinecone(api_key=api_key, environment=environment)
                 # 检查索引是否存在，不存在则创建（生产环境中需要更复杂的检查）
                 if index_name not in self.pc.list_indexes().names:
                     print(f"⚠️ 索引 '{index_name}' 不存在，正在创建 (使用 Serverless 配置)...")
                     # 创建一个使用 Serverless 配置的索引
                     self.pc.create_index(
                         name=index_name,
                         dimension=768, # 假设您的 Embedding 模型维度是 768 (例如 text-embedding-004)
                         metric='cosine',
                         spec=ServerlessSpec(cloud='aws', region='us-west-2')
                     )
                 self.index = self.pc.Index(index_name)
                 print(f"✅ 记忆库初始化：已连接到索引 '{index_name}'。RAG 激活！")
                 
                 # 初始化 Gemini Embedding Client (假设已配置 GEMINI_API_KEYS)
                 self.embed_client = genai.Client()
             except Exception as e:
                 print(f"❌ Pinecone 初始化失败: {e}. 切换到模拟模式。")
                 self.is_active = False
        
        if not self.is_active:
             print("⚠️ 记忆库初始化：VectorMemoryTool 处于模拟模式 (未配置 Key 或连接失败)。")

    def _get_embedding(self, text: str) -> List[float]:
        """使用 Gemini Embedding 模型获取向量。"""
        if not self.is_active:
             # 在模拟模式下返回一个模拟向量
             return [0.0] * 768 
        try:
             # 生产环境：调用 Gemini Embedding API
             response = self.embed_client.models.embed_content(
                 model=self.embedding_model,
                 content=text
             )
             return response['embedding']
        except Exception as e:
             print(f"❌ Embedding 失败: {e}")
             return []

    def store_output(self, task_id: str, content: str, agent_role: str):
        """将 Agent 产出分块、嵌入并存储。"""
        if self.is_active:
             # 生产环境：
             # 1. 分块 (为了简化，这里假设 content 就是一个块)
             # 2. 嵌入
             vector = self._get_embedding(content)
             if not vector:
                 print("⚠️ 存储失败：无法生成嵌入向量。")
                 return
                 
             # 3. 存储到 Pinecone
             try:
                 # 使用 UUID 作为 ID，task_id 作为元数据
                 vector_id = f"{agent_role}-{task_id}-{len(content)}"
                 self.index.upsert(
                     vectors=[{
                         "id": vector_id,
                         "values": vector,
                         "metadata": {"task_id": task_id, "agent": agent_role, "content": content[:100]}
                     }]
                 )
                 print(f"💾 {agent_role} 的产出已存储到语义记忆库 (RAG 激活)。")
             except Exception as e:
                 print(f"❌ 存储到 Pinecone 失败: {e}")
                 pass
        else:
             print(f"💾 {agent_role} 的产出已存储到语义记忆库 (模拟)。")
             pass

    def retrieve_context(self, task_id: str, query: str, top_k: int = 5) -> str:
        """根据查询和任务 ID 检索最相关的上下文。"""
        if self.is_active:
             # 生产环境：
             # 1. 查询 -> 嵌入
             query_vector = self._get_embedding(query)
             if not query_vector:
                 return f"检索失败：无法生成查询向量。"

             # 2. 向量搜索 (使用 task_id 进行过滤，确保只检索当前任务相关的记忆)
             try:
                 results = self.index.query(
                     vector=query_vector,
                     top_k=top_k,
                     filter={"task_id": {"$eq": task_id}},
                     include_metadata=True
                 )
                 
                 context_texts = [match['metadata']['content'] for match in results['matches'] if match['score'] > 0.7] # 仅返回高相关性结果
                 
                 if context_texts:
                      return "检索结果：\n" + "\n---\n".join(context_texts)
                 else:
                      return f"检索结果：[RAG] 数据库中未找到关于 '{query}' 的精确上下文。"
             except Exception as e:
                 return f"❌ Pinecone 检索失败: {e}"

        else:
             return "" # 模拟空检索结果

    def delete_task_memory(self, task_id: str):
        """
        根据任务 ID 删除所有相关的语义记忆 (向量)。
        此方法用于实现 RAG 数据的生命周期管理。
        """
        if self.is_active:
             # 生产环境：使用向量数据库的元数据过滤功能批量删除
             try:
                 self.index.delete(filter={"task_id": {"$eq": task_id}})
                 print(f"🗑️ 记忆库清理：已删除任务 ID '{task_id}' 下的所有语义记忆 (RAG 激活)。")
             except Exception as e:
                 print(f"❌ Pinecone 删除失败: {e}")
        else:
             print(f"🗑️ 记忆库清理：任务 ID '{task_id}' 清理完成 (模拟模式)。")
