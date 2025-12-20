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
    
    # [Robustness Fix] 检查文件是否存在，不存在则抛出异常，方便快速定位配置错误
    if not os.path.exists(path):
        abs_path = os.path.abspath(path)
        error_msg = f"❌ [Critical Configuration Error] Prompt file not found at: {abs_path}"
        print(error_msg)
        raise FileNotFoundError(error_msg)
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"⚠️ Warning: Failed to read prompt file {path}: {e}")
        raise e

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
        # [Performance Fix] 移除 deepcopy 以避免复制大量 Base64 图片数据
        # 改为浅拷贝 (传递引用)，既保证性能又防止顶层字典被意外修改
        "existing_code": global_state.code_blocks.copy(),
        "existing_artifacts": global_state.artifacts.copy(),
        "prefetch_cache": global_state.prefetch_cache,
        # 传递当前的向量时钟快照
        "parent_vector_clock": global_state.vector_clock.copy()
    }
    
    # 2. 准备该 Crew 专属的写入区域
    
    return {
        "read_only": read_only_context,
        "crew_identity": crew_name,
        # 传递 Trace ID 等元数据
        "meta": {
            "source_node": global_state.active_node_id,
            "slice_timestamp": global_state.vector_clock.get("main", 0)
        }
    }
