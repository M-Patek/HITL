import os
from typing import Dict, Any, List, Optional
# 确保从 common_types 导入 BaseAgent 和 State
from agents.common_types import BaseAgent, State
from workflow.graph import GraphDefinition


class OrchestratorAgent(BaseAgent):
    """
    The Orchestrator Agent is responsible for receiving the user's initial request 
    and determining which crew (Content Crew, Coding Crew, Data Crew) is best 
    suited to handle the task.
    """

    def __init__(self, llm_client: Any, all_crews: Dict[str, GraphDefinition]):
        super().__init__(llm_client)
        self.all_crews = all_crews
        self.system_prompt = self._load_system_prompt()
        self.tools = []

    def _load_system_prompt(self) -> str:
        """Loads the orchestrator system prompt from a markdown file."""
        import os

        # Construct path to the prompt file
        prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
        prompt_path = os.path.join(prompt_dir, "orchestrator.md")

        try:
            # 读取基础提示，并去除首尾空白
            with open(prompt_path, "r", encoding="utf-8") as f:
                base_prompt = f.read().strip()
        except FileNotFoundError:
            print(f"Error: Prompt file not found at {prompt_path}")
            base_prompt = "You are an expert workflow orchestrator." # Fallback prompt

        # 生成可用 crew 列表
        available_crews = "\n" + "\n".join(
            [f"- {crew_name}: {crew.description}" for crew_name, crew in self.all_crews.items()]
        ) + "\n"
        
        # 确保路径分隔符不会引起问题
        safe_prompt_dir = prompt_dir.replace('\\', '/')

        # 使用传统字符串拼接和 format() 来避免 f-string 解析问题
        final_prompt_template = """
{base_prompt}

# Available Crews
You MUST select a crew from the list below:
{available_crews}

# Context
The full directory for the crew prompts is at: {safe_prompt_dir}
        """
        
        final_prompt = final_prompt_template.format(
            base_prompt=base_prompt,
            available_crews=available_crews,
            safe_prompt_dir=safe_prompt_dir
        )
        
        self.prompt = final_prompt.strip()
        return self.prompt

    # [Fix] 修改 run 方法签名，只接收 state，并从中提取 user_input
    def run(self, state: State) -> Dict[str, Any]:
        """
        Processes the user's request and determines the next step.
        """
        # 从 state 中获取 project_state 对象
        project_state = state.get("project_state")
        # 从 project_state 中提取 user_input
        user_input = project_state.user_input if project_state else ""
        
        # 1. Prepare message history
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]
        
        # 2. Define the crew selection tool schema (dynamic based on all_crews)
        crew_names = list(self.all_crews.keys())
        crew_names_str = ", ".join(crew_names)
        
        tool_schema = {
            "type": "function",
            "function": {
                "name": "select_crew",
                "description": f"Select the best crew to handle the user's request from the list: {crew_names_str}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crew_name": {
                            "type": "string",
                            "enum": crew_names,
                            "description": "The name of the crew selected to handle the task.",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "A brief explanation for why this crew was selected."
                        }
                    },
                    "required": ["crew_name", "reasoning"],
                },
            }
        }
        
        # 3. Call the LLM with the tool
        # 注意：这里我们使用 self.llm_client，它已经在基类中被设置
        response = self.llm_client.generate_with_tool_use(
            messages=messages,
            tools=[tool_schema]
        )

        # 4. Process the tool call
        if response and response.tool_calls:
            tool_call = response.tool_calls[0]
            if tool_call.function.name == "select_crew":
                crew_name = tool_call.function.args.get("crew_name")
                reasoning = tool_call.function.args.get("reasoning", "No reasoning provided.")
                
                if crew_name in self.all_crews:
                    print(f"\n--- Orchestrator Selected Crew: {crew_name} (Reason: {reasoning}) ---")
                    return {
                        "next_crew": crew_name,
                        "initial_prompt": user_input,
                        "orchestrator_reasoning": reasoning,
                    }
                else:
                    return {
                        "error": f"Orchestrator selected an invalid crew: {crew_name}. Available crews: {crew_names_str}",
                        "next_crew": "human_intervention"
                    }
        else:
            print("\n--- Orchestrator Failed to Select Crew (Model didn't use the tool) ---")
            return {
                "error": "Orchestrator failed to use the 'select_crew' tool.",
                "next_crew": "human_intervention"
            }
