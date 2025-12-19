from langchain_core.messages import HumanMessage, AIMessage
from core.models import AgentState
from core.rotator import rotator
from tools.sandbox import run_python_code
from core.sig_ha import sig_ha # Import SIG-HA

# Prompts
def load_prompt(name):
    with open(f"agents/crews/coding_crew/prompts/{name}.md", "r") as f:
        return f.read()

PROMPT_CODER = load_prompt("coder")
PROMPT_REVIEWER = load_prompt("reviewer")

def coding_node(state: AgentState) -> AgentState:
    print(f"\n💻 [Coding Crew] Generating Code...")
    
    # SIG-HA Tracing
    sig_ha.update_trace_in_state(state, "CodingAgent")
    
    llm = rotator.get_model("gemini-2.0-flash-exp")
    
    # Basic coding logic
    messages = [
        {"role": "system", "content": PROMPT_CODER},
        {"role": "user", "content": f"Plan: {state.plan}\n\nHistory: {state.messages[-1].content}"}
    ]
    
    response = llm.invoke(messages)
    code = response.content
    
    # Extract code block (simple parsing)
    import re
    code_blocks = re.findall(r"```python(.*?)```", code, re.DOTALL)
    if code_blocks:
        clean_code = code_blocks[0].strip()
        state.code_snippets.append(clean_code)
        # Execute in sandbox
        result = run_python_code(clean_code)
        output_msg = f"Code Generated:\n{clean_code}\n\nExecution Result:\n{result}"
    else:
        output_msg = code
        
    state.messages.append(AIMessage(content=output_msg))
    return state

def review_node(state: AgentState) -> AgentState:
    print(f"\n👀 [Coding Crew] Reviewing Code...")
    
    # SIG-HA Tracing
    sig_ha.update_trace_in_state(state, "CodeReviewerAgent")
    
    llm = rotator.get_model("gemini-2.0-flash-exp")
    
    messages = [
        {"role": "system", "content": PROMPT_REVIEWER},
        {"role": "user", "content": f"Recent Code Output: {state.messages[-1].content}"}
    ]
    
    response = llm.invoke(messages)
    state.messages.append(response)
    
    return state
