from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from core.models import AgentState
from config.keys import load_gemini_api_key
from core.rotator import rotator
from core.sig_ha import sig_ha  # Import SIG-HA

# Load prompt
with open("agents/orchestrator/prompts/orchestrator.md", "r") as f:
    ORCHESTRATOR_PROMPT = f.read()

def call_orchestrator(state: AgentState) -> AgentState:
    """
    The Brain: Decides the next step and updates the cryptographic trace.
    """
    print(f"\n🧠 [Orchestrator] Analyzing request... (Depth: {state.trace_depth})")
    
    # 1. SIG-HA Tracing: Prove that Orchestrator is active
    # This mathematically signs the state BEFORE decision making
    sig_ha.update_trace_in_state(state, "OrchestratorAgent")
    print(f"🔐 [SIG-HA] State Signed. Fingerprint: {state.trace_t[:16]}...")

    # 2. Prepare Context
    messages = state.messages
    if not messages:
        messages = [HumanMessage(content=state.user_input)]
    
    # 3. Smart Routing (Model Selection)
    # Orchestrator uses Flash for speed, unless task is super complex (could use Pro)
    llm = rotator.get_model("gemini-2.0-flash-exp")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", ORCHESTRATOR_PROMPT),
        ("placeholder", "{messages}"),
    ])
    
    chain = prompt | llm
    
    # 4. Invoke LLM
    response = chain.invoke({"messages": messages})
    
    # 5. Parse Decision (Simple Heuristic for Demo)
    content = response.content
    state.plan = content
    state.messages.append(AIMessage(content=content))
    
    # Logic to determine next step based on content
    # (In a real app, use structured output or tool calling)
    if "CODING_CREW" in content:
        state.next_step = "coding_crew"
    elif "DATA_CREW" in content:
        state.next_step = "data_crew"
    elif "CONTENT_CREW" in content:
        state.next_step = "content_crew"
    elif "SEARCH" in content:
        # Internal tool call example
        state.next_step = "search_tool"
    else:
        state.next_step = "end"
        
    print(f"👉 [Router] Next Route: {state.next_step}")
    
    return state
