# 🏦 Bank POC: Agentic AI for Fixed Deposits

Welcome to the **Bank POC Agentic AI** repository. This project is a Proof of Concept (POC) demonstrating how a Multi-Agent AI system can automate financial research, risk assessment, and return projections for Fixed Deposit (FD) products. 

It uses **CrewAI** for agent orchestration, **LangChain** with **NVIDIA NIM** (Llama 3.1 405b) for intelligence, and **Streamlit** for a user-friendly web interface.

---

## 🚀 Quick Start & Installation

The main application code is located in the `poc/` directory. Follow these steps to run the application locally.

### 1. Prerequisites
* Python 3.9 or higher
* An [NVIDIA API Key](https://build.nvidia.com/) (to access the Llama 3.1 405b model)

### 2. Setup Instructions

Clone the repository and navigate to the `poc` folder:
```bash
git clone [https://github.com/Ganeshkumar-1508/bank_poc_agentic_ai.git](https://github.com/Ganeshkumar-1508/bank_poc_agentic_ai.git)
cd bank_poc_agentic_ai/poc


** Install Required Dependencies**

pip install -r requirements.txt

Create a .env file in your project, and there mention your secret api keys needed for the Project setup

**EX**
NVIDIA_API_KEY=your_nvidia_api_key_here

Navigate to the POC directory and to host your UI mention the following command

streamlit run app.py


**System Architecture & Roadmap**

This project is being developed in phases based on our System Architecture design.

**Phase 1: Current Implementation (The Engine)**

The current POC successfully implements the core analytical engine.

**Orchestration Engine (CrewAI):** A sequential process chaining 5 specialized AI agents (fd_crew.py).

**Chat UI / CLI:** A responsive Streamlit dashboard (app.py) for user input (Amount, Tenure) and result visualization.

**LLM Integration:** Powered by NVIDIA NIM (meta/llama-3.1-405b-instruct).

**Live Web Tools:** Integration with DuckDuckGo to fetch real-time FD rates and the latest banking news.

Financial Math Tool: Python-based fd_projection tool to ensure 100% accurate compound interest calculations without LLM hallucinations.

 **Phase 2: Future Roadmap (The Platform)**

The following components from the system architecture are planned for the next development phase to transition this POC into a full-scale banking assistant:

**Manager Agent (NLU & Intention): **A routing agent to understand natural language user intents (e.g., "Invest in FD" vs "Update KYC") and dynamically trigger the right workflow.

**KYC & Compliance Agents:** Dedicated agents to handle identity verification, document validation, and regulatory checks.

**Database Integration (RDBMS & Vector):** Persistent storage for user profiles, transaction histories, and customized financial advice.

**Document Processing:** OCR and Vision capabilities allow users to upload IDs and bank statements for analysis.

**Notification Channels:** Automated alerts (Email, SMS, WhatsApp) for deposit proofs, maturity reminders, and rate updates.
