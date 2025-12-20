import os
import re
import json  # [Fix] Import json
from typing import Dict, Any
from agents.common_types import AgentGraphState
from core.rotator import GeminiKeyRotator
from config.keys import GEMINI_MODEL_NAME
from core.utils import load_prompt
from core.crew_registry import crew_registry

async def orchestrator_node(state: AgentGraphState, rotator: GeminiKeyRotator) -> Dict[str, Any]:
    """
    [Orchestrator] 总指挥节点 (Async)
    """
    ps = state["project_state"]
    print(f"\n🧠 [Orchestrator] 正在规划任务: {ps.user_input}")
    
    base_prompt_path = os.path.join(os.path.dirname(__file__), "prompts")
    prompt_template = load_prompt(base_prompt_path, "orchestrator.md")
    
    # [🔥 Upgrade] 动态获取当前系统注册的所有工具能力描述
    available_tools_desc = crew_registry.get_crew_descriptions()
    
    if not available_tools_desc:
        available_tools_desc = "No specific crews registered. Please respond with 'finish'."
    
    dynamic_instruction = f"""
    Currently registered Crews and their capabilities:
    {available_tools_desc}
    
    Decide which Crew to delegate the task to.
    Output ONLY the Crew name (e.g., 'coding_crew') or 'finish' if the task is done or impossible.
    """
    
    formatted_prompt = prompt_template.format(
        user_input=ps.user_input
    )
    full_prompt = f"{formatted_prompt}\n\n{dynamic_instruction}"

    response = await rotator.call_gemini_with_rotation(
        model_name=GEMINI_MODEL_NAME,
        contents=[{"role": "user", "parts": [{"text": full_prompt}]}],
        system_instruction="You are the system orchestrator. Select the single best crew for the job.",
        complexity="simple"
    )
    
    # [Fix] Robust JSON Parsing Logic
    decision_data = {}
    if response:
        try:
            # 1. 剥离 Markdown 代码块
            clean_str = response.strip()
            if "```json" in clean_str:
                match = re.search(r"```json(.*?)```", clean_str, re.DOTALL)
                if match:
                    clean_str = match.group(1).strip()
            elif "```" in clean_str:
                match = re.search(r"```(.*?)```", clean_str, re.DOTALL)
                if match:
                    clean_str = match.group(1).strip()
            
            # 2. 解析 JSON
            decision_data = json.loads(clean_str)
        except json.JSONDecodeError:
            print(f"   ⚠️ Orchestrator JSON parse failed. Raw: {response[:50]}...")
            # Fallback: 尝试直接解析字符串作为 finish (针对非 JSON 的简单回复)
            if "finish" in response.lower():
                decision_data = {"next_agent": "finish"}

    # 3. 提取字段并验证
    next_agent_raw = decision_data.get("next_agent", "finish").lower().strip()
    instruction = decision_data.get("instruction", "No instruction provided.")
    reasoning = decision_data.get("reasoning", "No reasoning provided.")

    # 验证 Agent 是否存在
    all_crews = crew_registry.get_all_crews()
    target_agent = "finish"
    
    if next_agent_raw in all_crews:
        target_agent = next_agent_raw
    elif next_agent_raw == "finish":
        target_agent = "finish"
    else:
        print(f"   ⚠️ 未知指令 '{next_agent_raw}'，默认为 finish")

    print(f"   👉 指挥决定: {target_agent} | 原因: {reasoning[:50]}...")
    
    # [Fix] Ensure next_step is a structured Dictionary
    ps.next_step = {
        "agent_name": target_agent,
        "instruction": instruction,
        "reasoning": reasoning
    }
    ps.router_decision = target_agent
    
    return {
        "project_state": ps
    }
