from typing import List
from core.protocol import ToolDefinition

class ToolRegistry:
    """
    [Phase 1] Tool Metadata Registry
    集中管理所有工具的 JSON Schema 定义。
    [Fix] Memory Schema aligned with actual implementation in memory.py
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
            "description": "长期记忆库 (RAG)。支持语义检索 (Retrieve) 和 知识存储 (Store)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型：'retrieve' (查) 或 'store' (存)。",
                        "enum": ["retrieve", "store"]
                    },
                    "query": {
                        "type": "string",
                        "description": "检索关键词 (当 action='retrieve' 时必填)。用于查找相似的历史记录。"
                    },
                    "content": {
                        "type": "string",
                        "description": "要存储的文本内容 (当 action='store' 时必填)。"
                    },
                    "task_id": {
                        "type": "string",
                        "description": "关联的任务 ID (当 action='store' 时必填)。"
                    },
                    "agent_role": {
                        "type": "string",
                        "description": "存储数据的 Agent 角色名 (当 action='store' 时必填)。"
                    }
                },
                "required": ["action"]
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
