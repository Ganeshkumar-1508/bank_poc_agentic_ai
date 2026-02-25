
##  Getting Started

### Prerequisites

-   Python 3.10+
-   NVIDIA API Key (Get one from [NVIDIA NIM](https://build.nvidia.com/))
-   SMTP credentials (optional, for email features)

### Installation

1.  **Clone the repository**
    ```bash
    git clone https://github.com/Ganeshkumar-1508/bank_poc_agentic_ai.git
    cd POC
    ```

2.  **Create a virtual environment and install dependencies**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Set up Environment Variables**
    Create a `.env` file in the root directory:
    ```env
    NVIDIA_API_KEY=nvapi-xxxx...
    
    # Optional: For Email functionality
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=your-email@gmail.com
    SMTP_PASSWORD=your-app-password
    ```

4.  **Initialize the Database**
    Run the seed script to create the `bank_poc.db` database and populate it with dummy data.
    > **Note**: Ensure you have a `kyc_validation.py` file if required by `seed_dummy_data.py`, or modify the seed script to run without it if strictly testing.

    ```bash
    python seed_dummy_data.py
    ```

5.  **Run the Application**
    ```bash
    streamlit run app.py
    ```

##  Usage Scenarios

Once the app is running, you can interact with it using natural language:

### 1. Market Analysis & Recommendations
-   **Input**: *"I have 5 lakhs to invest for 2 years. Compare options for HDFC, SBI, and ICICI."*
-   **Result**: The Agent crew will search for current rates, calculate maturity amounts, assess risk based on news, and generate a detailed report with interactive charts.

### 2. Customer Onboarding
-   **Input**: *"I want to open a Fixed Deposit."* or *"I am an existing user with account 100000000001 and want to book an FD."*
-   **Flow**:
    1.  The Agent determines if you are a new or existing customer.
    2.  It asks for required details (Name, PAN, Amount, Tenure) conversationally.
    3.  It automatically fetches the latest interest rate for the requested bank.
    4.  It executes the backend transaction (deducting balance, creating FD record).
    5.  It generates a PDF and emails it to you (if SMTP is configured).

### 3. Database Queries
-   **Input**: *"Show me all active FDs."* or *"What is the total balance of user Amit Sharma?"*
-   **Result**: The DB Agent writes SQL queries to fetch and display the data from the local SQLite database.

##  The Agent Crew

The system uses a **Manager Agent** to route queries to the appropriate sub-teams:

1.  **Analysis Team**: `Query Parser` → `Search Agent` → `Researcher` → `Risk Analyst` → `Projection Agent` → `Strategist`.
2.  **Onboarding Team**: `Onboarding Agent` (Collects info) → `Email Specialist` (Sends PDF).
3.  **Database Team**: `DB Agent` (SQL Expert).

## Database Schema

The application uses a local SQLite database (`bank_poc.db`) with the following key tables:
-   `users`: Customer details.
-   `accounts`: Financial balances.
-   `fixed_deposit`: FD records linked to users.
-   `kyc_verification`: KYC status.
-   `address`: Customer addresses.

## Disclaimer

This project is for demonstration and educational purposes only. Financial data is fetched from public search results and may not be accurate. Use the code responsibly and verify all financial logic before applying it to real-world scenarios.

---
Built using CrewAI and Streamlit.
