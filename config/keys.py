import os
from typing import List
from dotenv import load_dotenv

# 确保在本模块被导入时也尝试加载一次 .env (双重保险)
load_dotenv()

# =======================================================
# 配置模块
# =======================================================

def get_env_list(key: str, default: str = "") -> List[str]:
    """辅助函数：安全地获取逗号分隔的环境变量列表"""
    raw_val = os.getenv(key, default)
    if not raw_val:
        return []
    return [k.strip() for k in raw_val.split(',') if k.strip()]

# 1. Gemini API Keys
# -------------------------------------------------------
# 如果环境变量未设置，这里将得到空列表 []
GEMINI_API_KEYS: List[str] = get_env_list("GEMINI_API_KEYS")

# 2. RAG (Pinecone) 配置
# -------------------------------------------------------
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "YOUR_PINECONE_API_KEY") 
PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "YOUR_PINECONE_ENVIRONMENT") 

# 3. 向量库参数
# -------------------------------------------------------
VECTOR_INDEX_NAME: str = os.getenv("VECTOR_INDEX_NAME", "agent-memory-index")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
