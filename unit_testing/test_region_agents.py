#!/usr/bin/env python
"""Test script to verify region-aware credit risk agents."""
import sys
sys.path.insert(0, '.')

from agents import create_credit_risk_agents

# Test India region
print('Testing India region agents...')
india_agents = create_credit_risk_agents(region='IN')
print(f'India agents created: {len(india_agents)} agents')
for key, agent in india_agents.items():
    print(f'  - Key: {key}')
    print(f'    Role: {agent.role}')
    print(f'    Tools: {agent.tools}')

# Test US region
print('\nTesting US region agents...')
us_agents = create_credit_risk_agents(region='US')
print(f'US agents created: {len(us_agents)} agents')
for key, agent in us_agents.items():
    print(f'  - Key: {key}')
    print(f'    Role: {agent.role}')
    print(f'    Tools: {agent.tools}')

print('\nTest completed successfully!')
print('\n=== VERIFICATION ===')
india_tools = str(india_agents['credit_risk_analyst_agent'].tools)
us_tools = str(us_agents['credit_risk_analyst_agent'].tools)
print('India region uses IndianCreditRiskScorerTool:', 'IndianCreditRiskScorerTool' in india_tools)
print('US region uses USCreditRiskScorerTool:', 'USCreditRiskScorerTool' in us_tools)