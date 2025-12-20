import pkgutil
import importlib
import os
import agents.crews as crews_package  # 确保 agents.crews 是一个 python package (有 __init__.py)
from typing import Dict, Any
from langgraph.graph.state import CompiledStateGraph

class CrewRegistry:
    """
    战队注册中心 (Singleton)
    负责自动发现 agents/crews 目录下的所有插件式 Crew。
    """
    _instance = None
    _crews: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CrewRegistry, cls).__new__(cls)
            cls._instance._discover_crews()
        return cls._instance

    def _discover_crews(self):
        """
        自动扫描 agents/crews 目录下的所有子模块。
        约定：每个 Crew 必须在其 __init__.py 或 graph.py 中暴露 'graph' 对象和 'meta' 信息。
        """
        print("🔍 [Registry] 正在扫描可插拔的 Crews...")
        
        # 兼容性处理：获取包路径
        if hasattr(crews_package, "__path__"):
            package_path = crews_package.__path__
        else:
            package_path = [os.path.dirname(crews_package.__file__)]

        for _, name, is_pkg in pkgutil.iter_modules(package_path):
            if is_pkg:
                try:
                    # 动态导入模块，例如 agents.crews.coding_crew
                    module_name = f"agents.crews.{name}"
                    module = importlib.import_module(module_name)
                    
                    # 1. 获取 Graph 对象
                    # 尝试从 __init__ 获取，如果失败则尝试从 graph.py 获取
                    crew_graph = getattr(module, "graph", None)
                    if not crew_graph:
                        try:
                            graph_module = importlib.import_module(f"{module_name}.graph")
                            crew_graph = getattr(graph_module, "graph", None)
                        except ImportError:
                            pass

                    # 2. 获取 Meta 信息
                    # 默认从 module.META 读取，没有则用默认值
                    meta = getattr(module, "META", {
                        "name": name,
                        "description": f"Handles tasks related to {name}.",
                        "trigger_phrases": [name]
                    })

                    # 3. 注册
                    if isinstance(crew_graph, CompiledStateGraph):
                        self._crews[name] = {
                            "graph": crew_graph,
                            "meta": meta,
                            "module": module
                        }
                        print(f"   ✅ 已注册组件: {name} \n      └─ 说明: {meta['description'].splitlines()[0]}...")
                    else:
                        print(f"   ⚠️ 跳过组件 {name}: 未找到有效的 CompiledStateGraph (变量名应为 'graph')")

                except Exception as e:
                    print(f"   ❌ 加载组件 {name} 失败: {e}")
        print("   🏁 扫描完成。")

    def get_all_crews(self) -> Dict[str, Dict[str, Any]]:
        """获取所有已注册的 crew"""
        return self._crews

    def get_crew_graph(self, name: str) -> CompiledStateGraph:
        """获取指定 crew 的 graph"""
        return self._crews.get(name, {}).get("graph")

    def get_crew_descriptions(self) -> str:
        """为 Orchestrator 生成动态的提示词"""
        descriptions = []
        for name, data in self._crews.items():
            desc = data['meta']['description']
            # 将多行描述合并为一行以便 Prompt 阅读
            desc_clean = desc.replace("\n", " ")
            descriptions.append(f"- **{name}**: {desc_clean}")
        return "\n".join(descriptions)

# 全局单例
crew_registry = CrewRegistry()
