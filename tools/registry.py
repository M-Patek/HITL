from typing import Dict, Any, List

class ToolRegistry:
    """
    [Phase 1] Tool Metadata Registry
    为 Orchestrator 提供标准化的工具描述 (JSON Schema)。
    """
    
    @staticmethod
    def get_google_search_schema() -> Dict[str, Any]:
        return {
            "name": "google_search",
            "description": "Search the internet for real-time information, technical docs, or facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string."
                    }
                },
                "required": ["query"]
            }
        }

    @staticmethod
    def get_sandbox_schema() -> Dict[str, Any]:
        return {
            "name": "python_sandbox",
            "description": "Execute Python code in a secure Docker container. Use this for calculation, data plotting, or algorithms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Complete, executable Python code script."
                    }
                },
                "required": ["code"]
            }
        }
    
    @staticmethod
    def get_memory_schema() -> Dict[str, Any]:
        return {
            "name": "vector_memory",
            "description": "Store or retrieve information from long-term vector database (RAG).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["store", "retrieve"],
                        "description": "Whether to save new info or query existing info."
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to store or the query string to retrieve."
                    }
                },
                "required": ["action", "content"]
            }
        }

    @classmethod
    def get_all_tool_schemas(cls) -> List[Dict[str, Any]]:
        """获取所有可用工具的 Schema 列表，供 LLM 绑定"""
        return [
            cls.get_google_search_schema(),
            cls.get_sandbox_schema(),
            cls.get_memory_schema()
        ]

    @staticmethod
    def get_tool_description_str() -> str:
        """为不支持 Function Calling 的纯 Prompt 模式提供文本描述"""
        return """
        1. google_search(query: str): Search internet for info.
        2. python_sandbox(code: str): Run Python code to calc/plot.
        3. vector_memory(action: 'store'|'retrieve', content: str): Access long-term memory.
        """
