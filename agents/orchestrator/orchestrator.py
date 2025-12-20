import os
import re
from typing import Dict, Any
from agents.common_types import BaseAgentState
from core.rotator import GeminiKeyRotator
from config.keys import GEMINI_MODEL_NAME
from core.utils import load_prompt
from core.crew_registry import crew_registry # [🔥 Plugin] 动态获取 Crew 信息

def orchestrator_node(state: BaseAgentState, rotator: GeminiKeyRotator) -> Dict[str, Any]:
    """
    [Orchestrator] 总指挥节点
    根据用户输入，动态选择最合适的 Crew (从 Registry 中获取)。
    """
    print(f"\n🧠 [Orchestrator] 正在规划任务: {state.get('user_input')}")
    
    base_prompt_path = os.path.join(os.path.dirname(__file__), "prompts")
    prompt_template = load_prompt(base_prompt_path, "orchestrator.md")
    
    # [🔥 Upgrade] 动态获取当前系统注册的所有工具能力描述
    available_tools_desc = crew_registry.get_crew_descriptions()
    
    # 如果没有注册任何 Crew，提供默认提示
    if not available_tools_desc:
        available_tools_desc = "No specific crews registered. Please respond with 'finish'."
    
    # 动态构造 System Instruction
    dynamic_instruction = f"""
    Currently registered Crews and their capabilities:
    {available_tools_desc}
    
    Decide which Crew to delegate the task to.
    Output ONLY the Crew name (e.g., 'coding_crew') or 'finish' if the task is done or impossible.
    """
    
    # 合并 Prompt
    formatted_prompt = prompt_template.format(
        user_input=state.get("user_input", "")
    )
    full_prompt = f"{formatted_prompt}\n\n{dynamic_instruction}"

    response = rotator.call_gemini_with_rotation(
        model_name=GEMINI_MODEL_NAME,
        contents=[{"role": "user", "parts": [{"text": full_prompt}]}],
        system_instruction="You are the system orchestrator. Select the single best crew for the job.",
        complexity="simple"
    )
    
    # 解析意图
    next_step = "finish"
    if response:
        cleaned_response = response.strip().lower()
        # 简单的清理逻辑，移除可能的标点和空白
        cleaned_response = re.sub(r"[^a-z_]", "", cleaned_response)
        
        # 检查是否存在于注册表中
        all_crews = crew_registry.get_all_crews()
        if cleaned_response in all_crews:
            next_step = cleaned_response
        elif "finish" in cleaned_response:
            next_step = "finish"
        else:
            print(f"   ⚠️ Orchestrator 返回了未知指令: {cleaned_response}, 默认为 finish")
            
    print(f"   👉 指挥决定: {next_step}")
    
    return {
        "next_step": next_step
    }
