import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def get_llm():
    """Initialize and return the LLM instance."""
    return ChatNVIDIA(
        model="nvidia_nim/meta/llama3-70b-instruct", 
        temperature=0,
        max_completion_tokens=1100
    )

def get_llm_lamma_vl():
    """Initialize and return the LLM instance."""
    return ChatNVIDIA(
        model="nvidia_nim/qwen/qwen3-next-80b-a3b-instruct", 
        temperature=0,
        max_completion_tokens=1100
    )


llm = get_llm()
lammavl = get_llm_lamma_vl()