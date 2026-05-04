# Bank POC Agentic AI (Django Implementation)

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0.4-green.svg)](https://www.djangoproject.com/)
[![CrewAI](https://img.shields.io/badge/CrewAI->=0.79.4-purple.svg)](https://www.crewai.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An AI-powered banking proof-of-concept application that leverages CrewAI multi-agent systems to automate loan underwriting, investment advisory, AML compliance, and financial analytics for both Indian and US markets.

---

## Table of Contents

- [About the Project](#about-the-project)
- [Tech Stack](#tech-stack)
- [Core Features](#core-features)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Contributing](#contributing)
- [License](#license)

---

## About the Project

This project addresses complexity and inefficiency in modern banking operations by automating:

- **Loan underwriting decisions** with region-specific ML models and RAG-based policy compliance
- **Investment product analysis** with real-time comparisons and risk assessments
- **AML compliance screening** with graph-based network analysis and sanctions checks
- **Real-time financial analytics** powered by multi-agent AI systems
- **Customer onboarding** with automated KYC and risk profiling

### Key Capabilities

- **Intelligent Routing**: LLM-based manager agents dynamically route tasks to specialized AI crews
- **Multi-Region Support**: Compliant with both Indian and US banking regulations
- **Automated Decision-Making**: Combines ML predictions with RAG-based policy compliance
- **Compliance Automation**: Full AML pipeline with Yente/OpenSanctions integration
- **Investment Advisory**: Real-time analysis of FD, RD, Mutual Funds, and NPS products

---

## Tech Stack

### Backend & Infrastructure

| Category             | Technologies                                     |
| -------------------- | ------------------------------------------------ |
| **Web Framework**    | Django 6.0.4, Django Channels (WebSocket)        |
| **Database**         | SQLite, Neo4j (Graph Database)                   |
| **Vector Store**     | ChromaDB == 1.1.1                                |
| **AI Orchestration** | CrewAI >= 0.79.4, LangChain                      |
| **LLM Providers**    | NVIDIA Llama-3.3-70B-Instruct, LiteLLM == 1.75.0 |
| **Observability**    | Langfuse                                         |

### Machine Learning

| Category                  | Technologies                                |
| ------------------------- | ------------------------------------------- |
| **ML Frameworks**         | XGBoost, Scikit-learn, Pandas, NumPy        |
| **Pre-trained Models**    | Fannie Mae ML Models                        |
| **Credit Risk**           | Custom trained models for Indian/US markets |
| **Customer Segmentation** | Clustering algorithms                       |
| **Portfolio Risk**        | Risk assessment models                      |

### Frontend

| Category            | Technologies                |
| ------------------- | --------------------------- |
| **Template Engine** | Django Templates            |
| **UI Framework**    | HTML5, CSS3, JavaScript     |
| **Visualization**   | Apache ECharts              |
| **Real-time**       | WebSocket (Django Channels) |

### External Integrations

| Category          | Services                      |
| ----------------- | ----------------------------- |
| **News & Data**   | NewsAPI, DuckDuckGo, Wikidata |
| **Compliance**    | Yente/OpenSanctions           |
| **Communication** | SMTP/Gmail                    |
| **API Style**     | RESTful API                   |

---

## Core Features

### 1. AI-Powered Loan Underwriting

- Region-specific credit risk models (Indian/US markets)
- RAG-based policy compliance checking
- Automated approval/rejection decisions
- Real-time credit score analysis
- Document verification via AI agents

### 2. Investment Advisory & Analysis

- Real-time comparison of FD, RD, Mutual Funds, and NPS
- Risk assessment based on customer profile
- Projected returns with visual analytics
- Market-aware investment recommendations
- Multi-agent analysis for comprehensive advice

### 3. AML Compliance Pipeline

- Neo4j graph-based network analysis
- Sanctions screening via Yente/OpenSanctions
- Ultimate Beneficial Owner (UBO) identification
- Automated PDF report generation
- Transaction monitoring and anomaly detection

### 4. Mortgage Analytics

- Fannie Mae ML model integration
- Customer segmentation analysis
- Portfolio risk assessment
- Regional performance tracking
- Operational efficiency metrics

### 5. Admin Dashboard & API

- Real-time crew execution tracking
- Bulk operations support
- Natural language database queries
- WebSocket-powered live updates
- Comprehensive audit logging

---

## Project Structure

```
bank_poc_agentic_ai_new_UI/Test/
├── bank_app/                    # Main Django application
│   ├── migrations/              # Database migrations
│   ├── templates/               # HTML templates
│   ├── static/                  # CSS, JavaScript, assets
│   ├── views/                   # View functions (modularized)
│   ├── models.py                # Database models
│   ├── admin_views.py           # Admin panel views
│   ├── api_views.py             # REST API endpoints
│   ├── consumers.py             # WebSocket consumers
│   └── routing.py               # WebSocket routing
├── bank_poc_django/             # Django project settings
│   ├── settings.py              # Configuration
│   ├── urls.py                  # URL routing
│   └── asgi.py                  # ASGI config for Channels
├── models/                      # ML models
│   ├── credit_risk/indian/      # Indian credit risk models
│   └── fannie_mae_models/       # Fannie Mae mortgage models
├── tools/                       # AI agent tools
│   ├── credit_risk_tool.py      # Credit risk assessment
│   ├── compliance_tool.py       # AML compliance checks
│   ├── neo4j_tool.py            # Graph database operations
│   ├── rag_policy_tool.py       # RAG policy enforcement
│   └── ...                      # Other specialized tools
├── agents.py                    # Agent definitions
├── crews.py                     # Crew configurations
├── tasks.py                     # Task definitions
├── rag_engine.py                # RAG implementation
├── langfuse_evaluator.py        # Langfuse evaluation
├── manage.py                    # Django management
└── requirements.txt             # Python dependencies
```

---

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager
- Git (optional, for version control)

### Step-by-Step Installation

1. **Navigate to the project directory:**

   ```bash
   cd bank_poc_agentic_ai_new_UI/Test
   ```

2. **Create and activate a virtual environment:**

   ```bash
   # Create virtual environment
   python -m venv venv

   # Activate on Windows
   venv\Scripts\activate

   # Activate on Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   - Copy the example environment file:
     ```bash
     copy example.env .env
     ```
   - Edit `.env` and add your API keys (see [Configuration](#configuration) section)

5. **Run database migrations:**

   ```bash
   python manage.py migrate
   ```

6. **Create a superuser for admin panel (optional):**

   ```bash
   python manage.py createsuperuser
   ```

7. **Start the development server:**

   ```bash
   python manage.py runserver <port_number>
   ```

8. **Access the application:**
   - Main UI: http://127.0.0.1:8000/
   - Admin Panel: http://127.0.0.1:8000/admin/
   - API Documentation: http://127.0.0.1:8000/api/

---

## Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# NVIDIA API Configuration
NVIDIA_API_KEY=your_nvidia_api_key_here

# Neo4j Graph Database Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password

# NewsAPI Configuration
NEWSAPI_API_KEY=your_newsapi_key_here

# Langfuse Observability Configuration
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

# Email Configuration (Gmail SMTP)
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
EMAIL_PORT=587
EMAIL_USE_TLS=True

# Optional: Additional Configuration
DEBUG=True
SECRET_KEY=your_django_secret_key
```

### Neo4j Setup

For AML compliance features, Neo4j must be running:

```bash
# Using Docker
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:latest
```

---

## Usage

### Investment Analysis Example

Query the investment advisory crew for fixed deposit recommendations:

```python
# Python example
from bank_app.api_views import query_investment_advisory

response = query_investment_advisory(
    amount=100000,
    tenure_months=12,
    risk_profile="moderate",
    region="IN"
)
print(response)
```

**cURL Example:**

```bash
curl -X POST http://127.0.0.1:8000/api/investment-advisory/ \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100000,
    "tenure_months": 12,
    "risk_profile": "moderate",
    "region": "IN"
  }'
```

### Loan Application Creation

Submit a loan application for AI-powered underwriting:

```python
# Python example
from bank_app.api_views import submit_loan_application

response = submit_loan_application(
    applicant_name="John Doe",
    annual_income=75000,
    credit_score=720,
    loan_amount=50000,
    loan_purpose="home",
    region="US"
)
print(response)
```

**cURL Example:**

```bash
curl -X POST http://127.0.0.1:8000/api/loan-application/ \
  -H "Content-Type: application/json" \
  -d '{
    "applicant_name": "John Doe",
    "annual_income": 75000,
    "credit_score": 720,
    "loan_amount": 50000,
    "loan_purpose": "home",
    "region": "US"
  }'
```

### AML Compliance Check

Run sanctions screening on a customer:

```python
# Python example
from bank_app.api_views import run_aml_compliance_check

response = run_aml_compliance_check(
    customer_name="Acme Corporation",
    country="US",
    beneficial_owners=[
        {"name": "Jane Smith", "ownership_percent": 60},
        {"name": "Bob Johnson", "ownership_percent": 40}
    ]
)
print(response)
```

**cURL Example:**

```bash
curl -X POST http://127.0.0.1:8000/api/aml-compliance/ \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Acme Corporation",
    "country": "US",
    "beneficial_owners": [
      {"name": "Jane Smith", "ownership_percent": 60},
      {"name": "Bob Johnson", "ownership_percent": 40}
    ]
  }'
```

### Credit Risk Assessment

Evaluate credit risk using ML models:

```python
# Python example
from bank_app.api_views import assess_credit_risk

response = assess_credit_risk(
    age=35,
    annual_income=80000,
    credit_score=750,
    loan_amount=25000,
    employment_years=8,
    region="IN"
)
print(response)
```

**cURL Example:**

```bash
curl -X POST http://127.0.0.1:8000/api/credit-risk/ \
  -H "Content-Type: application/json" \
  -d '{
    "age": 35,
    "annual_income": 80000,
    "credit_score": 750,
    "loan_amount": 25000,
    "employment_years": 8,
    "region": "IN"
  }'
```

### Natural Language Database Query

Query the database using natural language:

```bash
curl -X POST http://127.0.0.1:8000/api/db-query/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me all approved loans from last month"
  }'
```

---

## API Reference

### Base URL

```
http://127.0.0.1:8000/api/
```

### Endpoints

| Method | Endpoint                | Description                     |
| ------ | ----------------------- | ------------------------------- |
| `POST` | `/investment-advisory/` | Get investment recommendations  |
| `POST` | `/loan-application/`    | Submit loan application         |
| `POST` | `/aml-compliance/`      | Run AML compliance check        |
| `POST` | `/credit-risk/`         | Assess credit risk              |
| `POST` | `/db-query/`            | Natural language database query |
| `GET`  | `/crew-status/`         | Get crew execution status       |
| `GET`  | `/health/`              | Health check endpoint           |

### Response Format

All API responses follow a consistent JSON structure:

```json
{
  "success": true,
  "data": {
    // Response-specific data
  },
  "message": "Operation completed successfully",
  "timestamp": "2026-05-04T10:30:00Z"
}
```

### Error Responses

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input parameters"
  },
  "timestamp": "2026-05-04T10:30:00Z"
}
```

---

## Contributing

We welcome contributions to the Bank POC Agentic AI project! Here's how you can help:

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch:**
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Commit your changes:**
   ```bash
   git commit -m 'Add some amazing feature'
   ```
4. **Push to the branch:**
   ```bash
   git push origin feature/amazing-feature
   ```
5. **Open a Pull Request**

### Development Guidelines

- Follow PEP 8 style guidelines for Python code
- Write meaningful commit messages
- Add tests for new features
- Update documentation as needed
- Ensure all existing tests pass

### Reporting Bugs

Please use the issue tracker to report bugs. Include:

- A clear title and description
- Steps to reproduce the issue
- Expected vs. actual behavior
- Environment details (OS, Python version, etc.)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Support

For support, questions, or feedback:

- Open an issue on GitHub
- Contact the development team
- Check the documentation for common solutions

---

## Acknowledgments

- **CrewAI** - Multi-agent orchestration framework
- **LangChain** - LLM application development
- **NVIDIA** - LLM inference infrastructure
- **Neo4j** - Graph database technology
- **Pycaret** - Mortgage ML models
- **Apache ECharts** - Data visualization library

---

_Built with using Django, CrewAI, and cutting-edge AI technologies_
