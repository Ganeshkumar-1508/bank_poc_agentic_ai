# Bank POC Agentic AI - New UI

A comprehensive banking proof-of-concept application powered by CrewAI agents, featuring intelligent loan processing, FD management, and admin tools.

## Table of Contents

- [Getting Started](#getting-started)
- [New Features](#new-features)
- [Quick Start Guide](#quick-start-guide)
- [Documentation](#documentation)
- [Testing](#testing)
- [API Reference](#api-reference)
- [Database Schema](#database-schema)
- [Troubleshooting](#troubleshooting)
- [Disclaimer](#disclaimer)

## Getting Started

### Prerequisites

- Python 3.10+
- NVIDIA API Key (Get one from [NVIDIA NIM](https://build.nvidia.com/))
- SMTP credentials (optional, for email features)
- CrewAI for agent-based features

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Ganeshkumar-1508/bank_poc_agentic_ai.git
   cd bank_poc_agentic_ai
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r Test/requirements.txt
   ```

3. **Set up Environment Variables**
   Create a `.env` file in the root directory:
   ```env
   NVIDIA_API_KEY=nvapi-xxxx...
   
   # Optional: For Email functionality
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   
   # Django settings
   SECRET_KEY=your-secret-key
   DEBUG=True
   ```

4. **Initialize the Database**
   ```bash
   python Test/create_db.py
   python Test/seed_data.py
   ```

5. **Run the Application**
   ```bash
   # Django server
   cd Test
   python manage.py runserver
   
   # Or Streamlit app
   streamlit run streamlit_ref/app.py
   ```

## New Features

### Phase 7: Testing & Documentation

This release includes comprehensive integration tests and user documentation:

#### Integration Tests
- [`test_integration_smart_assistant.py`](unit_testing/test_integration_smart_assistant.py) - Smart Assistant chat flow tests
- [`test_integration_fd_advisor.py`](unit_testing/test_integration_fd_advisor.py) - FD Advisor enhanced features tests
- [`test_integration_loan_creation.py`](unit_testing/test_integration_loan_creation.py) - Loan Creation Crew workflow tests
- [`test_integration_fd_creation.py`](unit_testing/test_integration_fd_creation.py) - FD booking and certificate tests
- [`test_integration_email_campaigns.py`](unit_testing/test_integration_email_campaigns.py) - Email campaign management tests
- [`test_integration_database_query.py`](unit_testing/test_integration_database_query.py) - Database query interface tests

#### User Documentation
- [`docs/SMART_ASSISTANT_GUIDE.md`](docs/SMART_ASSISTANT_GUIDE.md) - Smart Assistant usage guide
- [`docs/FD_ADVISOR_ENHANCED_GUIDE.md`](docs/FD_ADVISOR_ENHANCED_GUIDE.md) - FD Advisor enhanced features guide
- [`docs/LOAN_APPLICATION_GUIDE.md`](docs/LOAN_APPLICATION_GUIDE.md) - Loan application process guide
- [`docs/FD_CREATION_GUIDE.md`](docs/FD_CREATION_GUIDE.md) - FD booking and certificate guide
- [`docs/ADMIN_EMAIL_CAMPAIGNS_GUIDE.md`](docs/ADMIN_EMAIL_CAMPAIGNS_GUIDE.md) - Email campaign management guide
- [`docs/ADMIN_DATABASE_QUERY_GUIDE.md`](docs/ADMIN_DATABASE_QUERY_GUIDE.md) - Database query interface guide
- [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md) - Complete API reference

### CrewAI Agent Features

#### Smart Assistant
Unified chat interface that routes queries to specialized agents:
- Natural language processing
- Intent detection and routing
- Session context maintenance
- Multi-step query handling

#### FD Advisor Enhanced
- Real-time rate comparison across banks
- Automated visualization generation
- FD template creation
- Maturity calculations with tax implications

#### Loan Creation Crew
- End-to-end loan processing
- Automated KYC verification
- Compliance screening (AML/PEP)
- Credit risk assessment
- Auto-approve/reject decisions

#### Admin Tools
- **Email Campaigns**: Bulk email with templates and tracking
- **Database Query Interface**: Natural language SQL queries with audit trail
- **Analytics Dashboard**: Real-time statistics and charts

## Quick Start Guide

### For End Users

#### 1. Making an FD Investment
1. Navigate to `/fd-advisor/`
2. Enter your investment amount and tenure
3. Compare rates across banks
4. Select preferred option and book
5. Receive PDF certificate via email

#### 2. Applying for a Loan
1. Go to `/new-account/` or use Smart Assistant
2. Fill in application details
3. Upload KYC documents
4. Receive instant decision (auto-approve/reject/review)
5. Track application status

#### 3. Using Smart Assistant
1. Visit `/smart-assistant/`
2. Type your query in natural language
3. Get instant responses and recommendations

### For Administrators

#### 1. Managing Email Campaigns
1. Access `/admin/email-campaigns/`
2. Create new campaign with template
3. Define target audience filters
4. Preview and send

#### 2. Running Database Queries
1. Go to `/admin/database-query/`
2. Enter natural language query
3. Review generated SQL
4. Execute and export results

## Documentation

### User Guides
- [Smart Assistant Guide](docs/SMART_ASSISTANT_GUIDE.md) - How to use the chat interface
- [FD Advisor Guide](docs/FD_ADVISOR_ENHANCED_GUIDE.md) - FD features and comparisons
- [Loan Application Guide](docs/LOAN_APPLICATION_GUIDE.md) - Complete loan process
- [FD Creation Guide](docs/FD_CREATION_GUIDE.md) - Booking FDs and certificates
- [Email Campaigns Guide](docs/ADMIN_EMAIL_CAMPAIGNS_GUIDE.md) - Admin email management
- [Database Query Guide](docs/ADMIN_DATABASE_QUERY_GUIDE.md) - Natural language queries

### Developer Documentation
- [API Documentation](docs/API_DOCUMENTATION.md) - All endpoints with examples
- [CrewAI Integration Guide](Test/docs/CREWAI_DJANGO_INTEGRATION.md) - Crew setup and usage
- [Testing Guide](Test/docs/CREWAI_FULL_TESTING_GUIDE.md) - Complete testing procedures

## Testing

### Running Integration Tests

```bash
# Navigate to unit_testing directory
cd unit_testing

# Run all tests
pytest -v

# Run specific test file
pytest test_integration_smart_assistant.py -v

# Run with coverage
pytest --cov=. -v
```

### Test Coverage

| Feature | Test File | Coverage |
|---------|-----------|----------|
| Smart Assistant | `test_integration_smart_assistant.py` | Query routing, session persistence, concurrent requests |
| FD Advisor | `test_integration_fd_advisor.py` | Rate lookup, comparison, visualization, templates |
| Loan Creation | `test_integration_loan_creation.py` | Application workflow, decisions, status transitions |
| FD Creation | `test_integration_fd_creation.py` | Booking, certificates, calculations, persistence |
| Email Campaigns | `test_integration_email_campaigns.py` | Campaign creation, templates, tracking |
| Database Query | `test_integration_database_query.py` | NL queries, safety validation, audit logging |

### Running Tests Against Live Server

```bash
# Set base URL environment variable
export TEST_BASE_URL=http://localhost:8000

# Run tests
pytest unit_testing/ -v -s
```

## API Reference

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/smart-assistant-query/` | POST | Smart Assistant chat |
| `/api/fd-advisor-crew/` | POST | FD rate analysis |
| `/api/loan-creation/` | POST | Loan application processing |
| `/api/router/` | POST | Query routing |
| `/api/analysis/` | POST | Data analysis |
| `/api/visualization/` | POST | Chart generation |
| `/api/fd-template/` | POST | Template generation |
| `/api/database-query/` | POST | Database queries |
| `/api/loan-list/` | GET | List loan applications |
| `/api/dashboard-stats/` | GET | Dashboard statistics |

See [API Documentation](docs/API_DOCUMENTATION.md) for complete reference.

## Database Schema

### Key Tables

- `loan_application` - Loan applications and status
- `fixed_deposit` - FD records
- `email_campaign` - Email campaign definitions
- `email_campaign_log` - Email delivery tracking
- `database_query_log` - Query audit trail
- `audit_log` - System audit logs
- `user_session` - User session data
- `kyc_document` - KYC documents
- `compliance_screening` - Compliance results

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "CrewAI not available" | Install: `pip install crewai crewai-tools` |
| "SMTP not configured" | Add SMTP settings to `.env` file |
| "Database not found" | Run `python Test/create_db.py` |
| "CSRF token missing" | Include CSRF token in POST requests |
| "Timeout errors" | Increase timeout or simplify queries |

### Getting Help

1. Check [documentation](#documentation) for your issue
2. Review [API documentation](docs/API_DOCUMENTATION.md) for endpoint details
3. Check admin panel logs for errors
4. Verify environment configuration

## Project Structure

```
bank_poc_agentic_ai/
├── Test/
│   ├── bank_app/           # Django app
│   │   ├── models.py       # Data models
│   │   ├── views.py        # View logic
│   │   ├── api_views.py    # API endpoints
│   │   └── admin_views.py  # Admin interfaces
│   ├── agents.py           # CrewAI agents
│   ├── tasks.py            # CrewAI tasks
│   ├── crews.py            # Crew definitions
│   └── tools/              # Tool implementations
├── unit_testing/           # Integration tests
│   ├── test_integration_smart_assistant.py
│   ├── test_integration_fd_advisor.py
│   ├── test_integration_loan_creation.py
│   ├── test_integration_fd_creation.py
│   ├── test_integration_email_campaigns.py
│   └── test_integration_database_query.py
├── docs/                   # Documentation
│   ├── SMART_ASSISTANT_GUIDE.md
│   ├── FD_ADVISOR_ENHANCED_GUIDE.md
│   ├── LOAN_APPLICATION_GUIDE.md
│   ├── FD_CREATION_GUIDE.md
│   ├── ADMIN_EMAIL_CAMPAIGNS_GUIDE.md
│   ├── ADMIN_DATABASE_QUERY_GUIDE.md
│   └── API_DOCUMENTATION.md
├── streamlit_ref/          # Streamlit UI reference
└── models/                 # ML models
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Submit a pull request

## License

This project is for demonstration and educational purposes only.

## Disclaimer

This project is for demonstration and educational purposes only. Financial data is fetched from public sources and may not be accurate. Use the code responsibly and verify all financial logic before applying it to real-world scenarios.

---

Built with Django, CrewAI, and Streamlit.

*Last updated: 2026-05-01*
