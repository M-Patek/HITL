import os
from typing import Dict, Any, List, Optional
from core.models import LLMClient
from agents.common_types import BaseAgent, State
from workflow.graph import GraphDefinition


class OrchestratorAgent(BaseAgent):
    """
    The Orchestrator Agent is responsible for receiving the user's initial request 
    and determining which crew (Content Crew, Coding Crew, Data Crew) is best 
    suited to handle the task.
    """

    def __init__(self, llm_client: LLMClient, all_crews: Dict[str, GraphDefinition]):
        super().__init__(llm_client)
        self.all_crews = all_crews
        self.system_prompt = self._load_system_prompt()
        self.tools = []

    def _load_system_prompt(self) -> str:
        """Loads the orchestrator system prompt from a markdown file."""
        import os # Re-import inside method for safety, though it's already at the top

        # Construct path to the prompt file
        prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
        prompt_path = os.path.join(prompt_dir, "orchestrator.md")

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                base_prompt = f.read().strip() # Added .strip() to clean up whitespace
        except FileNotFoundError:
            print(f"Error: Prompt file not found at {prompt_path}")
            base_prompt = "You are an expert workflow orchestrator." # Fallback prompt

        # Generate the list of available crews for the prompt
        available_crews = "\n" + "\n".join(
            [f"- {crew_name}: {crew.description}" for crew_name, crew in self.all_crews.items()]
        ) + "\n"

        # **最终修复：避免复杂的 f-string，改用传统拼接**
        # 避免在多行 f-string 中嵌入包含反斜杠的变量
        final_prompt = f"""
{base_prompt}

# Available Crews
You MUST select a crew from the list below:
{available_crews}

# Context
The full directory for the crew prompts is at: {prompt_dir.replace('\\', '/')}
        """
        self.prompt = final_prompt.strip()
        return self.prompt # 返回 self.prompt

    # ... (rest of the class methods)
    def run(self, state: State, user_input: str) -> Dict[str, Any]:
        """
        Processes the user's request and determines the next step.

        The Orchestrator's job is to select the most appropriate crew 
        (based on the Crew Selection Tool) and assign the original 
        user request to that crew's entry point.
        """
        
        # 1. Prepare message history
        # For the orchestrator, we only provide the initial user prompt.
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
        # The Orchestrator's job is always to call this tool.
        # We rely on the model to use the tool correctly to proceed.
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
                
                # Check if the selected crew is valid
                if crew_name in self.all_crews:
                    print(f"\n--- Orchestrator Selected Crew: {crew_name} (Reason: {reasoning}) ---")
                    return {
                        "next_crew": crew_name,
                        "initial_prompt": user_input,
                        "orchestrator_reasoning": reasoning,
                    }
                else:
                    # Fallback if model selects an invalid crew name
                    return {
                        "error": f"Orchestrator selected an invalid crew: {crew_name}. Available crews: {crew_names_str}",
                        "next_crew": "human_intervention" # Signal for a manual review/correction
                    }
        else:
            # Fallback if model failed to use the tool
            print("\n--- Orchestrator Failed to Select Crew (Model didn't use the tool) ---")
            return {
                "error": "Orchestrator failed to use the 'select_crew' tool.",
                "next_crew": "human_intervention" # Signal for a manual review/correction
            }
