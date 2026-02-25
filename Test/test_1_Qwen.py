import os
import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool  
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from dotenv import load_dotenv
import json
import re

# Load environment variables
load_dotenv()

# ======================
# CUSTOM TOOL WRAPPER (Fixes Pydantic Validation Error)
# ======================
class DuckDuckGoSearchTool(BaseTool):
    """
    Custom tool wrapper that properly inherits from CrewAI's BaseTool
    This fixes the Pydantic validation error by implementing required methods
    """
    name: str = "Web Search"
    description: str = "Searches the web for current fixed deposit rates, bank news, and safety information"
    
    def _run(self, query: str) -> str:
        """
        Execute the search using LangChain's DuckDuckGoSearchRun
        """
        try:
            search = DuckDuckGoSearchRun()
            results = search.run(query)
            return results
        except Exception as e:
            return f"Search failed: {str(e)}"
    
    async def _arun(self, query: str) -> str:
        """Async version of the search"""
        return self._run(query)

# ======================
# LLM Setup (NVIDIA NIM)
# ======================
@st.cache_resource
def get_llm():
    """Initialize NVIDIA NIM LLM with proper configuration"""
    try:
        return ChatNVIDIA(
            model="meta/llama3-70b-instruct",
            base_url=os.getenv("NIM_BASE_URL", "https://api.nvcf.nvidia.com/v2/nvcf"),
            api_key=os.getenv("NVIDIA_API_KEY"),
            temperature=0.3,
            max_tokens=2000
        )
    except Exception as e:
        st.error(f"NVIDIA LLM initialization failed: {str(e)}")
        st.stop()

# ======================
# Tools Setup (Now using Custom Wrapper)
# ======================
# ✅ CORRECT TOOL SETUP - Using custom BaseTool wrapper
search_tool = DuckDuckGoSearchTool()  # Now this is a valid BaseTool instance

# ======================
# Agents Definition
# ======================
def create_agents(llm):
    """Create all agents with proper tool configuration"""
    
    research_agent = Agent(
        role="Fixed Deposit Research Specialist",
        goal="Identify top 10 fixed deposit providers in India with highest interest rates for given amount and tenure",
        backstory=(
            "Expert financial researcher with 10+ years analyzing Indian banking products. "
            "Specializes in comparing FD rates across public sector banks, private banks, and NBFCs. "
            "Always cross-verifies rates from official bank websites and RBI sources."
        ),
        tools=[search_tool],  # ✅ Now properly wrapped
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
    
    safety_agent = Agent(
        role="Financial Safety Analyst",
        goal="Evaluate safety ratings, regulatory compliance, and recent news for FD providers",
        backstory=(
            "Former RBI compliance officer with expertise in bank stability assessment. "
            "Monitors CRILC reports, credit ratings (CRISIL/CARE/ICRA), and regulatory actions. "
            "Categorizes institutions based on Deposit Insurance (DICGC) coverage and financial health."
        ),
        tools=[search_tool],  # ✅ Now properly wrapped
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
    
    analyst_agent = Agent(
        role="Fixed Deposit Financial Analyst",
        goal="Calculate accurate maturity amounts and create visual projections for FD investments",
        backstory=(
            "Chartered Financial Analyst specializing in fixed income instruments. "
            "Expert in compounding calculations, tax implications, and inflation-adjusted returns. "
            "Creates professional visualizations for investment comparison."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
    
    return research_agent, safety_agent, analyst_agent

# ======================
# Tasks Definition
# ======================
def create_tasks(amount, tenure, research_agent, safety_agent, analyst_agent):
    """Create sequential tasks for the FD analysis workflow"""
    
    research_task = Task(
        description=(
            f"Research CURRENT fixed deposit interest rates in India for ₹{amount:,.0f} for {tenure} years tenure.\n"
            "Focus on:\n"
            "- Top 10 providers (include public sector banks, private banks, and NBFCs)\n"
            "- Exact interest rates for this amount bracket\n"
            "- Senior citizen rates (if applicable)\n"
            "- Compounding frequency (quarterly/annually)\n"
            "- Minimum/maximum deposit limits\n"
            "- Official source URLs for verification\n\n"
            "CRITICAL: Only include rates verified from official bank websites or RBI sources from the last 30 days."
        ),
        expected_output=(
            "JSON array with exactly 10 providers containing:\n"
            "- bank: Full bank name\n"
            "- rate: Annual interest rate (float)\n"
            "- senior_rate: Senior citizen rate if available\n"
            "- min_amount: Minimum deposit required\n"
            "- compounding: 'quarterly' or 'annually'\n"
            "- source_url: Official source URL\n"
            "- last_updated: Date of rate verification"
        ),
        agent=research_agent,
        async_execution=False
    )
    
    safety_task = Task(
        description=(
            "For each bank from research results, analyze:\n"
            "1. DICGC insurance coverage status\n"
            "2. Latest credit rating (CRISIL/CARE/ICRA)\n"
            "3. News from last 6 months (financial stability, regulatory actions, fraud cases)\n"
            "4. RBI compliance status\n"
            "5. Capital adequacy ratio if available\n\n"
            "Categorize each as:\n"
            "- SAFE: DICGC insured + investment-grade rating + no negative news\n"
            "- MODERATE: DICGC insured but lower rating or minor concerns\n"
            "- RISKY: Not DICGC insured or major regulatory issues\n\n"
            "Banks to analyze: {banks_list}"
        ),
        expected_output=(
            "JSON array with safety assessment for each bank containing:\n"
            "- bank: Bank name\n"
            "- safety_rating: 'SAFE' | 'MODERATE' | 'RISKY'\n"
            "- dicgc_covered: true/false\n"
            "- credit_rating: Rating agency and grade\n"
            "- recent_news_summary: 1-sentence summary of relevant news\n"
            "- risk_factors: Array of specific concerns (empty if none)"
        ),
        agent=safety_agent,
        async_execution=False
    )
    
    analysis_task = Task(
        description=(
            "Calculate FD projections for ₹{amount} over {tenure} years using provider data.\n"
            "Perform calculations:\n"
            "1. Maturity amount = P * (1 + r/n)^(n*t)\n"
            "   - P = principal, r = rate, n = compounding periods/year, t = years\n"
            "2. Total interest earned\n"
            "3. Post-tax returns (assuming 30% tax bracket)\n"
            "4. Inflation-adjusted return (assume 5.5% inflation)\n"
            "5. Year-by-year growth projection\n\n"
            "Generate data for 3 visualizations:\n"
            "- Bar chart: Principal vs Interest for top 5 providers\n"
            "- Line chart: Yearly growth trajectory\n"
            "- Horizontal bar: Rate comparison"
        ),
        expected_output=(
            "JSON object containing:\n"
            "- maturity_data: Array of {bank, rate, principal, interest, maturity, safety_rating}\n"
            "- yearly_projection: Array of {year, amount} for top provider\n"
            "- rate_comparison: Array of {bank, rate} sorted descending\n"
            "- key_insights: Array of 3-5 bullet points with investment recommendations"
        ),
        agent=analyst_agent,
        async_execution=False
    )
    
    return research_task, safety_task, analysis_task

# ======================
# Data Processing Helpers
# ======================
def parse_json_output(raw_output):
    """Safely extract JSON from LLM output"""
    try:
        # Try direct JSON parse first
        return json.loads(raw_output)
    except json.JSONDecodeError:
        # Extract JSON from markdown code blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', raw_output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        # Try to find any JSON-like structure
        json_match = re.search(r'\[.*\]|\{.*\}', raw_output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        raise ValueError("Could not parse JSON from output")

def calculate_maturity(principal, rate, tenure, compounding='quarterly'):
    """Calculate FD maturity amount with proper compounding"""
    r = rate / 100
    t = tenure
    
    if compounding == 'quarterly':
        n = 4
        maturity = principal * (1 + r/n)**(n*t)
    else:  # annually
        n = 1
        maturity = principal * (1 + r)**t
    
    return round(maturity, 2)

# ======================
# Visualization Functions
# ======================
def plot_maturity_breakdown(data):
    """Create bar chart for principal vs interest"""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Sort by maturity amount
    sorted_data = sorted(data, key=lambda x: x['maturity'], reverse=True)[:5]
    banks = [d['bank'] for d in sorted_data]
    principals = [d['principal'] for d in sorted_data]
    interests = [d['interest'] for d in sorted_data]
    
    x = np.arange(len(banks))
    width = 0.35
    
    ax.bar(x - width/2, principals, width, label='Principal', color='#2E86AB', alpha=0.9)
    ax.bar(x + width/2, interests, width, label='Interest', color='#A23B72', alpha=0.9)
    
    ax.set_xlabel('Banks', fontsize=12, fontweight='bold')
    ax.set_ylabel('Amount (₹)', fontsize=12, fontweight='bold')
    ax.set_title('Maturity Amount Breakdown (Top 5 Providers)', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(banks, rotation=30, ha='right')
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for i, (p, i_val) in enumerate(zip(principals, interests)):
        total = p + i_val
        ax.text(i, total + total*0.01, f'₹{total:,.0f}', 
                ha='center', va='bottom', fontweight='bold', fontsize=9)
    
    plt.tight_layout()
    return fig

def plot_yearly_growth(data, tenure):
    """Create line chart for yearly growth projection"""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Get top provider
    top_provider = max(data, key=lambda x: x['maturity'])
    principal = top_provider['principal']
    rate = top_provider['rate']
    
    # Calculate yearly values
    years = list(range(0, tenure + 1))
    amounts = [calculate_maturity(principal, rate, y, 'quarterly') for y in years]
    
    ax.plot(years, amounts, marker='o', linewidth=2.5, markersize=8, 
            color='#2E86AB', label=f"{top_provider['bank']} @ {rate}%")
    
    # Fill area under curve
    ax.fill_between(years, principal, amounts, alpha=0.2, color='#2E86AB')
    
    ax.set_xlabel('Years', fontsize=12, fontweight='bold')
    ax.set_ylabel('Investment Value (₹)', fontsize=12, fontweight='bold')
    ax.set_title(f'Yearly Growth Projection: ₹{principal:,.0f} → ₹{amounts[-1]:,.0f}', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Add final value annotation
    ax.annotate(f'₹{amounts[-1]:,.0f}', xy=(tenure, amounts[-1]), 
                xytext=(tenure-0.5, amounts[-1]*1.05),
                fontsize=11, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5))
    
    plt.tight_layout()
    return fig

def plot_rate_comparison(data):
    """Create horizontal bar chart for rate comparison"""
    fig, ax = plt.subplots(figsize=(10, 7))
    
    # Sort by rate descending and take top 8
    sorted_data = sorted(data, key=lambda x: x['rate'], reverse=True)[:8]
    banks = [d['bank'] for d in sorted_data]
    rates = [d['rate'] for d in sorted_data]
    colors = ['#06A77D' if r >= 7.5 else '#F5A623' if r >= 7.0 else '#D0021B' for r in rates]
    
    y_pos = np.arange(len(banks))
    bars = ax.barh(y_pos, rates, color=colors, alpha=0.9, edgecolor='black', linewidth=0.5)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(banks)
    ax.set_xlabel('Interest Rate (%)', fontsize=12, fontweight='bold')
    ax.set_title('Interest Rate Comparison (Top Providers)', fontsize=14, fontweight='bold', pad=20)
    ax.invert_yaxis()  # Highest rate at top
    
    # Add rate labels on bars
    for i, (bar, rate) in enumerate(zip(bars, rates)):
        ax.text(rate + 0.05, bar.get_y() + bar.get_height()/2, 
                f'{rate:.2f}%', 
                va='center', fontweight='bold', fontsize=10)
    
    # Add threshold lines
    ax.axvline(x=7.0, color='green', linestyle='--', alpha=0.5, label='Good Rate (7%+)')
    ax.axvline(x=7.5, color='darkgreen', linestyle='--', alpha=0.5, label='Excellent Rate (7.5%+)')
    ax.legend(loc='lower right')
    
    plt.tight_layout()
    return fig

# ======================
# Streamlit UI
# ======================
def main():
    st.set_page_config(
        page_title="FD Advisor Pro",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Sidebar for configuration
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3144/3144457.png", width=100)
        st.title("⚙️ Configuration")
        
        st.subheader("NVIDIA NIM Settings")
        nim_base_url = st.text_input(
            "NIM Base URL", 
            value=os.getenv("NIM_BASE_URL", "https://api.nvcf.nvidia.com/v2/nvcf"),
            type="password"
        )
        nvidia_api_key = st.text_input(
            "NVIDIA API Key", 
            value=os.getenv("NVIDIA_API_KEY", ""),
            type="password"
        )
        
        if not nvidia_api_key:
            st.warning("⚠️ NVIDIA API Key required for analysis")
            st.stop()
        
        # Save to environment
        os.environ["NIM_BASE_URL"] = nim_base_url
        os.environ["NVIDIA_API_KEY"] = nvidia_api_key
        
        st.markdown("---")
        st.subheader("ℹ️ About")
        st.info(
            "This tool analyzes current FD rates from top Indian banks with safety assessment "
            "and return projections. All data is sourced in real-time via web search."
        )
        st.markdown(
            "*Data as of: " + datetime.now().strftime("%d %B %Y") + "*"
        )
    
    # Main UI
    st.title("💰 Fixed Deposit Investment Advisor")
    st.markdown("""
    <div style='background-color:#e8f4f8; padding:15px; border-radius:10px; margin-bottom:20px;'>
        <h4>✨ Smart FD Analysis with Safety Ratings & Projections</h4>
        <p>Get personalized recommendations for your fixed deposit investment with real-time rate comparison, 
        safety analysis, and maturity projections.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # User input section
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        amount = st.number_input(
            "Investment Amount (₹)", 
            min_value=1000, 
            max_value=10000000, 
            value=50000,
            step=1000,
            format="%d"
        )
    with col2:
        tenure = st.slider(
            "Tenure (Years)", 
            min_value=1, 
            max_value=10, 
            value=2,
            step=1
        )
    with col3:
        is_senior = st.checkbox("Senior Citizen (60+ years)", value=False)
    
    st.markdown("---")
    
    if st.button("🔍 Analyze FD Options", type="primary", use_container_width=True, icon="🚀"):
        # Initialize LLM
        llm = get_llm()
        
        # Create agents
        research_agent, safety_agent, analyst_agent = create_agents(llm)
        
        # Create tasks
        research_task, safety_task, analysis_task = create_tasks(
            amount, tenure, research_agent, safety_agent, analyst_agent
        )
        
        # Execute research task
        with st.spinner("📡 Researching current FD rates from top banks..."):
            research_crew = Crew(
                agents=[research_agent],
                tasks=[research_task],
                verbose=2,
                process=Process.sequential
            )
            research_output = research_crew.kickoff()
            
            try:
                providers = parse_json_output(research_output.raw)
                if not isinstance(providers, list) or len(providers) < 5:
                    raise ValueError("Insufficient provider data returned")
                
                # Extract bank names for safety analysis
                bank_names = [p['bank'] for p in providers[:10]]
            except Exception as e:
                st.error(f"❌ Research failed: {str(e)}")
                st.code(research_output.raw[:500] + "...", language="json")
                st.stop()
        
        # Execute safety task
        with st.spinner("🛡️ Analyzing bank safety and regulatory status..."):
            safety_task.description = safety_task.description.replace(
                "{banks_list}", ", ".join(bank_names)
            )
            safety_crew = Crew(
                agents=[safety_agent],
                tasks=[safety_task],
                verbose=2,
                process=Process.sequential
            )
            safety_output = safety_crew.kickoff()
            
            try:
                safety_ratings = parse_json_output(safety_output.raw)
                # Create safety lookup dict
                safety_lookup = {item['bank']: item for item in safety_ratings}
            except Exception as e:
                st.warning(f"Safety analysis incomplete: {str(e)}")
                safety_lookup = {}
        
        # Execute analysis task
        with st.spinner("📊 Calculating maturity amounts and projections..."):
            # Prepare provider data with safety ratings
            enriched_providers = []
            for provider in providers[:8]:  # Top 8 for analysis
                bank = provider['bank']
                rate = provider.get('senior_rate', provider['rate']) if is_senior else provider['rate']
                maturity = calculate_maturity(amount, rate, tenure, provider.get('compounding', 'quarterly'))
                
                enriched_providers.append({
                    'bank': bank,
                    'rate': rate,
                    'principal': amount,
                    'interest': round(maturity - amount, 2),
                    'maturity': round(maturity, 2),
                    'safety_rating': safety_lookup.get(bank, {}).get('safety_rating', 'UNKNOWN'),
                    'dicgc_covered': safety_lookup.get(bank, {}).get('dicgc_covered', True)
                })
            
            analysis_task.description = analysis_task.description.replace(
                "{amount}", str(amount)
            ).replace(
                "{tenure}", str(tenure)
            )
            
            analysis_crew = Crew(
                agents=[analyst_agent],
                tasks=[analysis_task],
                verbose=2,
                process=Process.sequential
            )
            analysis_output = analysis_crew.kickoff()
            
            try:
                analysis_data = parse_json_output(analysis_output.raw)
                maturity_data = analysis_data.get('maturity_data', enriched_providers)
            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")
                maturity_data = enriched_providers
        
        # ======================
        # Display Results
        # ======================
        st.success("✅ Analysis complete! Here are your personalized FD recommendations")
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            best_rate = max(maturity_data, key=lambda x: x['rate'])
            st.metric("🏆 Best Rate", f"{best_rate['rate']:.2f}%", best_rate['bank'])
        with col2:
            max_maturity = max(maturity_data, key=lambda x: x['maturity'])
            st.metric("💰 Max Maturity", f"₹{max_maturity['maturity']:,.0f}", 
                     f"+₹{max_maturity['interest']:,.0f} interest")
        with col3:
            safe_count = sum(1 for p in maturity_data if p['safety_rating'] == 'SAFE')
            st.metric("🛡️ Safe Options", f"{safe_count}/{len(maturity_data)}", 
                     "DICGC Insured")
        with col4:
            avg_rate = sum(p['rate'] for p in maturity_data) / len(maturity_data)
            st.metric("📈 Avg. Rate", f"{avg_rate:.2f}%", 
                     f"vs Inflation 5.5%")
        
        st.markdown("---")
        
        # Top Recommendations Table
        st.subheader("🏦 Top 5 Recommended Providers")
        
        # Prepare display data
        display_data = []
        for provider in sorted(maturity_data, key=lambda x: x['maturity'], reverse=True)[:5]:
            safety_emoji = "✅ SAFE" if provider['safety_rating'] == 'SAFE' else \
                          "⚠️ MODERATE" if provider['safety_rating'] == 'MODERATE' else "❌ RISKY"
            
            display_data.append({
                "Bank": provider['bank'],
                "Interest Rate": f"{provider['rate']:.2f}%",
                "Maturity Amount": f"₹{provider['maturity']:,.0f}",
                "Total Interest": f"₹{provider['interest']:,.0f}",
                "Safety": safety_emoji,
                "DICGC Insured": "✅ Yes" if provider.get('dicgc_covered', True) else "❌ No"
            })
        
        df = pd.DataFrame(display_data)
        st.dataframe(
            df.style.applymap(
                lambda x: 'background-color: #d4edda' if '✅ SAFE' in str(x) else 
                         'background-color: #fff3cd' if '⚠️ MODERATE' in str(x) else 
                         'background-color: #f8d7da' if '❌ RISKY' in str(x) else '',
                subset=['Safety']
            ).format({
                'Maturity Amount': lambda x: x,
                'Total Interest': lambda x: x
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # Visualizations
        st.markdown("---")
        st.subheader("📈 Investment Projections")
        
        viz_col1, viz_col2 = st.columns(2)
        
        with viz_col1:
            st.markdown("### Interest Rate Comparison")
            st.pyplot(plot_rate_comparison(maturity_data))
        
        with viz_col2:
            st.markdown("### Maturity Breakdown (Top 5)")
            st.pyplot(plot_maturity_breakdown(maturity_data))
        
        st.markdown("### Yearly Growth Projection")
        st.pyplot(plot_yearly_growth(maturity_data, tenure))
        
        # Safety Deep Dive
        st.markdown("---")
        st.subheader("🛡️ Safety Analysis Deep Dive")
        
        for provider in sorted(maturity_data, key=lambda x: x['maturity'], reverse=True)[:3]:
            bank = provider['bank']
            safety_info = safety_lookup.get(bank, {})
            
            with st.expander(f"{bank} - {provider['rate']:.2f}% | Safety: {provider['safety_rating']}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Financial Safety**")
                    st.write(f"- DICGC Insured: {'✅ Yes' if provider.get('dicgc_covered', True) else '❌ No'}")
                    st.write(f"- Credit Rating: {safety_info.get('credit_rating', 'Not available')}")
                
                with col2:
                    st.markdown("**Recent Developments**")
                    news = safety_info.get('recent_news_summary', 'No recent news found')
                    st.write(f"📰 {news}")
                    
                    risks = safety_info.get('risk_factors', [])
                    if risks:
                        st.markdown("**⚠️ Risk Factors**")
                        for risk in risks[:3]:  # Show top 3 risks
                            st.write(f"- {risk}")
                    else:
                        st.success("✅ No significant risk factors identified")
                
                st.markdown("**💡 Recommendation**")
                if provider['safety_rating'] == 'SAFE':
                    st.success(f"**Recommended** for conservative investors. DICGC insured with strong financials.")
                elif provider['safety_rating'] == 'MODERATE':
                    st.warning(f"**Consider** if seeking higher returns. Verify DICGC coverage before investing.")
                else:
                    st.error(f"**Not Recommended** for FDs. Consider only if you fully understand the risks.")
        
        # Key Insights
        st.markdown("---")
        st.subheader("💡 Key Investment Insights")
        
        insights = [
            f"🔹 **Best Risk-Adjusted Return**: {max_maturity['bank']} offers ₹{max_maturity['maturity']:,.0f} maturity with {'SAFE' if max_maturity['safety_rating'] == 'SAFE' else 'MODERATE'} rating",
            "🔹 **Inflation Reality**: Even at 7.5% FD rate, post-tax returns (~5.25%) barely beat inflation (5.5%)",
            "🔹 **Safety First**: Always prioritize DICGC-insured banks (covers up to ₹5 lakh per depositor per bank)",
            "🔹 **Senior Citizens**: You qualify for 0.25-0.75% higher rates at most banks - always declare your age!",
            "🔹 **Tax Tip**: For amounts > ₹5 lakh, consider splitting FDs across banks to maximize DICGC coverage"
        ]
        
        for insight in insights:
            st.info(insight)
        
        # Disclaimer
        st.markdown("---")
        st.caption("""
        <div style='background-color:#fff8e6; padding:15px; border-radius:8px; border-left:4px solid #ffc107;'>
        <strong>⚠️ Important Disclaimer:</strong><br>
        • Interest rates are subject to change without notice. Verify rates on official bank websites before investing.<br>
        • FD interest is taxable as per your income tax slab. TDS applies if interest > ₹40,000/year (₹50,000 for seniors).<br>
        • DICGC insurance covers up to ₹5 lakh per depositor per bank (principal + interest combined).<br>
        • This analysis is for informational purposes only and not financial advice. Consult a SEBI-registered advisor.<br>
        • Data sourced via web search on {date}. Rates may have changed since.
        </div>
        """.format(date=datetime.now().strftime("%d %B %Y")), unsafe_allow_html=True)

if __name__ == "__main__":
    main()