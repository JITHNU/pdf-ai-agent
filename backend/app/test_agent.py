from typing import TypedDict, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    messages: List[HumanMessage]

os.environ["GOOGLE_API_KEY"] = "AIzaSyCzApWZcifrgPNludXSws-E71bG7TpvRgw"

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0
)

def Chatbot(state: AgentState) -> AgentState:
    response = llm.invoke(state["messages"])
    print(f"\nJithBot: {response.content}")
    # Append the AI’s message back into the state
    state["messages"].append(AIMessage(content=response.content))
    return state

workflow = StateGraph(AgentState)

workflow.add_node("Chatbot", Chatbot)
workflow.set_entry_point("Chatbot")
workflow.add_edge("Chatbot", END)

app = workflow.compile()

print("🤖 JithBot is online! Type 'exit' to quit.\n")

history = [
    SystemMessage(content=(
        "You are JithBot, a friendly AI assistant. "
        "You should always respond as JithBot and never mention that you are trained by Google or any other company. "
        "Always answer as if you are a personal assistant created by Jithnuka Weerasinghe."
    ))
]

while True:
    user_input = input("You: ")

    if user_input.lower() in ["exit", "quit"]:
        print("Goodbye!")
        break

    history.append(HumanMessage(content=user_input))
    result = app.invoke({"messages": history}) 
