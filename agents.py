from crewai import Agent, Task, Crew, Process, LLM
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL


def _build_llm() -> LLM:
    return LLM(
        model="nvidia_nim/meta/llama3-8b-instruct",
        api_key=NVIDIA_API_KEY,
        base_url=NVIDIA_BASE_URL,
        temperature=0.2,
    )


def run_consultant_summary(context: str) -> str:
    if not NVIDIA_API_KEY:
        return "NVIDIA_API_KEY is not set. Add it to .env to enable the consultant summary."

    llm = _build_llm()

    consultant = Agent(
        role="Consultant Agent",
        goal="Summarize FD/TD options from the provided context for the user.",
        backstory="You extract the most relevant tenure and rate highlights.",
        llm=llm,
        verbose=True,
    )

    task = Task(
        description=(
            "Summarize the FD options in the context. Keep it concise and helpful."
            f"Context:{context}"
        ),
        expected_output="A short summary of key rate/tenure options.",
        agent=consultant,
        
    )

    crew = Crew(
        agents=[consultant],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )

    return str(crew.kickoff())
