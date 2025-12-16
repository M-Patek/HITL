import os
from typing import List

# =======================================================
# 1. Gemini API Keys (从 .env 文件加载)
# =======================================================

# 从环境变量中获取以逗号分隔的 Key 字符串，然后分割成列表
# 默认使用空列表，以防止 key 未配置时程序崩溃
GEMINI_API_KEYS: List[str] = os.getenv("GEMINI_API_KEYS", "").split(',')
# 移除可能存在的空字符串或空格
GEMINI_API_KEYS = [k.strip() for k in GEMINI_API_KEYS if k.strip()]


# =======================================================
# 2. 外部工具配置 (RAG - Pinecone)
# =======================================================

# 🚨 从环境变量中获取 Pinecone 配置，如果未配置将使用占位符，VectorMemoryTool 将进入模拟模式
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "YOUR_PINECONE_API_KEY") 
PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "YOUR_PINECONE_ENVIRONMENT") 
VECTOR_INDEX_NAME: str = os.getenv("VECTOR_INDEX_NAME", "agent-memory-index")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
