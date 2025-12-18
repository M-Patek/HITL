from typing import List
from core.protocol import ToolDefinition

class ToolRegistry:
    """
    [Phase 1] Tool Metadata Registry
    集中管理所有工具的 JSON Schema 定义。
    """
    
    @staticmethod
    def get_google_search_schema() -> ToolDefinition:
        return {
            "name": "google_search",
            "description": "联网搜索工具。用于获取实时信息、技术文档、新闻或事实核查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词。应精简且具体，支持中英文。"
                    }
                },
                "required": ["query"]
            }
        }

    @staticmethod
    def get_sandbox_schema() -> ToolDefinition:
        return {
            "name": "python_sandbox",
            "description": "Python 代码沙箱。用于执行计算、数据分析、绘图或运行算法。支持 pandas, matplotlib, numpy 等库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "完整的、可执行的 Python 代码字符串。代码应包含必要的 import 语句。"
                    }
                },
                "required": ["code"]
            }
        }
    
    @staticmethod
    def get_memory_schema() -> ToolDefinition:
        return {
            "name": "vector_memory",
            "description": "长期记忆库 (RAG)。用于存储重要的知识片段或检索之前的项目经验。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型：'store' (存储) 或 'retrieve' (检索)。",
                        "enum": ["store", "retrieve"]
                    },
                    "content": {
                        "type": "string",
                        "description": "要存储的文本内容，或者用于检索的查询语句。"
                    }
                },
                "required": ["action", "content"]
            }
        }

    @classmethod
    def get_all_tool_schemas(cls) -> List[ToolDefinition]:
        """获取所有可用工具的 Schema 列表，供 LLM Function Calling 使用"""
        return [
            cls.get_google_search_schema(),
            cls.get_sandbox_schema(),
            cls.get_memory_schema()
        ]
