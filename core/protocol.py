from typing import TypedDict, List, Dict, Any, Literal, Optional

class ToolProperty(TypedDict, total=False):
    """参数属性描述"""
    type: str
    description: str
    enum: Optional[List[str]]

class ToolParameters(TypedDict):
    """参数集合描述 (JSON Schema Object)"""
    type: Literal["object"]
    properties: Dict[str, ToolProperty]
    required: List[str]

class ToolDefinition(TypedDict):
    """标准工具定义接口"""
    name: str
    description: str
    parameters: ToolParameters
