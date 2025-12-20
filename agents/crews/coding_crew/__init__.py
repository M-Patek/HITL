from agents.crews.coding_crew.graph import graph

# [🔥 Plugin Architecture] 
# 这是 Coding Crew 对外暴露的“名片”。
# Registry 会读取这个 META 信息来告诉 Orchestrator 这个 Crew 能干什么。

META = {
    "name": "coding_crew",
    "description": "专精于软件开发任务的精英团队。拥有以下能力：\n1. 编写高质量 Python 代码\n2. 在沙箱环境中执行和测试代码\n3. 自动进行代码审查和 Debug\n4. 具备自我修复能力 (Reflector)，能解决复杂报错。\n适用于：写脚本、数据处理代码、算法实现、Bug修复等。",
    "trigger_phrases": ["code", "python", "debug", "implement", "script", "program"]
}

__all__ = ["graph", "META"]
