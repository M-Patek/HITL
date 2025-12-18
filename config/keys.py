import os

# --- Gateway & API Configuration ---
GATEWAY_API_BASE = os.getenv("GATEWAY_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai/")
GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "") # Google AI Studio Key

# --- Vector DB ---
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "swarm-memory")

# --- Model Tiers [Protocol Phase 1] ---
# TIER 1: 高速、低成本。适用于分类、简单总结、搜索查询生成。
TIER_1_FAST = "gemini-2.5-flash-preview-09-2025"

# TIER 2: 强推理、高上下文。适用于复杂代码生成、深度分析、Orchestrator 决策。
# (In production, change this to 'gemini-1.5-pro' or 'gemini-ultra')
TIER_2_PRO = "gemini-2.5-flash-preview-09-2025" 

# Default fallback
GEMINI_MODEL_NAME = TIER_2_PRO
