import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def get_llm():
    return ChatNVIDIA(
        model="nvidia_nim/meta/llama3-70b-instruct", 
        temperature=0,
        max_completion_tokens=1100
    )

def get_llm_2():
    return ChatNVIDIA(
        model="nvidia_nim/qwen/qwen3-235b-a22b", 
        temperature=0.4,
    )


llm = get_llm()
llm_2 = get_llm_2()