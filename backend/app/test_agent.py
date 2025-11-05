from typing import TypedDict, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.pregel import Pregel


class AgentState(TypedDict):
    messages: List[HumanMessage]

# Set API key
os.environ["GOOGLE_API_KEY"] = "YOUR_API_KEY_HERE"

# Initialize model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0
)

# Define the model node
def Chatbot(state: AgentState) -> AgentState:
    response = llm.invoke(state["messages"])
    print(f"\nJithBot: {response.content}")
    return state

# Use `state_key` to annotate the main state, avoids __start__ errors
workflow = StateGraph(AgentState, state_key="messages")

workflow.add_node("Chatbot", Chatbot)
workflow.set_entry_point("Chatbot")  # Entry point replaces START edge
workflow.add_edge("Chatbot", END)    # End edge

print("🤖 JithBot is online! Type 'exit' to quit.")

# Conversation history
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
    result = workflow.invoke({"messages": history})
    
    # Get the latest AI response
    ai_message = result["messages"][-1].content
    print(f"\n")
    history.append(AIMessage(content=ai_message))
