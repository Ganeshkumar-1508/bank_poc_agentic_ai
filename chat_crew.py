from crewai import Crew, Process, Task

class ChatCrew:
    def __init__(self):
        self.agents = []
        self.tasks = []

    def kickoff(self, user_message):
        from agents import intent_agent

        chat_task = Task(
            description=f"User Query: {user_message}. Analyze this query. If it requires FD data, use the available tool to fetch it.",
            expected_output="A helpful response to the user. If data was fetched, include the CSV data in the response.",
            agent=intent_agent
        )
        
        crew = Crew(
            agents=[intent_agent],
            tasks=[chat_task],
            process=Process.sequential,
            verbose=True
        )
        
        return crew.kickoff()