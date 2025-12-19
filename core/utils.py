import os
import copy
from typing import Dict, Any, Optional

# 为了类型提示，但在运行时避免循环导入，可以使用 TYPE_CHECKING
# from core.models import ProjectState 

def load_prompt(base_path: str, filename: str) -> str:
    """
    通用 Prompt 文件加载工具。
    遵循 DRY (Don't Repeat Yourself) 原则，统一处理文件读取和异常。
    """
    path = os.path.join(base_path, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"⚠️ Warning: Prompt file {path} not found.")
        return ""

def slice_state_for_crew(global_state: Any, crew_name: str) -> Dict[str, Any]:
    """
    [Phase 1 New] 状态切片 (State Slicing)
    为并行执行的 Crew 创建局部状态视图。
    
    Args:
        global_state (ProjectState): 当前全局项目状态对象
        crew_name (str): 目标 Crew 的名称 (e.g., 'coding_crew')
        
    Returns:
        Dict: 包含传递给 Crew 的必要上下文
    """
    # 1. 提取只读的全局上下文
    read_only_context = {
        "task_id": global_state.task_id,
        "root_instruction": global_state.root_node.instruction,
        "existing_code": copy.deepcopy(global_state.code_blocks),
        "existing_artifacts": copy.deepcopy(global_state.artifacts),
        "prefetch_cache": global_state.prefetch_cache,
        # 传递当前的向量时钟快照
        "parent_vector_clock": global_state.vector_clock.copy()
    }
    
    # 2. 准备该 Crew 专属的写入区域 (通常是空的或者是接续之前的)
    # 注意：这里我们通过 active_node 的 local_history 来作为 Crew 的“记忆”
    # 如果 Crew 需要从之前的进度继续，它会从 node_map 中找到对应的节点
    
    return {
        "read_only": read_only_context,
        "crew_identity": crew_name,
        # 传递 Trace ID 等元数据
        "meta": {
            "source_node": global_state.active_node_id,
            "slice_timestamp": global_state.vector_clock.get("main", 0)
        }
    }
