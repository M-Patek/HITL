from typing import List

# =======================================================
# 1. Gemini API Keys (已填充您的 10 个 Key)
# =======================================================
GEMINI_API_KEYS: List[str] = [
]

# =======================================================
# 2. 外部工具配置 (生产环境配置)
# =======================================================

# 🚨 请替换为您真实的 Pinecone 或其他向量数据库 Key
PINECONE_API_KEY: str = "YOUR_PINECONE_API_KEY" 
PINECONE_ENVIRONMENT: str = "YOUR_PINECONE_ENVIRONMENT" 
VECTOR_INDEX_NAME: str = "agent-memory-index"
EMBEDDING_MODEL: str = "text-embedding-004"
