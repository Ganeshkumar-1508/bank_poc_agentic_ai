# FD Advisor Enhancement - Wireframe Options

## Current Layout (Baseline)
```
┌─────────────────────────────────────────────────────────────┐
│  💰 Fixed Deposit Advisor                                    │
│  Compare FD Rates Across Banks                               │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐  │
│  │  🏦 FD Comparison                                      │  │
│  │  ───────────────────────────────────────────────────  │  │
│  │  Investment Amount: [slider + input]                   │  │
│  │  Tenure: [slider + input]                              │  │
│  │  Region: [dropdown]                                    │  │
│  │  [Compare Rates button]                                │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Results Panel (currently shows basic comparison table)│  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Option 1: Single Unified Panel (Inline Charts)
**Best for:** Cohesive narrative flow, users who want analysis + visuals together

```
┌─────────────────────────────────────────────────────────────┐
│  Results Panel                                               │
│  ─────────────────────────────────────────────────────────  │
│  ## Investment Analysis                                      │
│  For ₹1,00,000 over 12 months in India:                     │
│                                                              │
│  ### Top 5 Providers                                         │
│  | Provider    | Rate  | Senior Rate | Safety    |          │
│  |-------------|-------|-------------|-----------|          │
│  | HDFC Bank   | 7.25% | 7.75%       | Very High |          │
│  | SBI         | 7.00% | 7.50%       | Highest   |          │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ### Rate Comparison Chart                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  [ECharts Bar Chart - Rates by Provider]            │    │
│  │                                                     │    │
│  │  HDFC  ████████████ 7.25%                           │    │
│  │  SBI   ██████████   7.00%                           │    │
│  │  ...                                                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ### Strategic Recommendations                               │
│  - HDFC offers best rate for general customers              │
│  - SBI recommended for senior citizens (government-backed)  │
│  - Consider laddering strategy for liquidity...             │
│                                                              │
│  ### Risk Analysis                                           │
│  - All providers DICGC insured up to ₹5 lakhs               │
│  - HDFC: NBFC - moderate credit risk                        │
│  ─────────────────────────────────────────────────────────  │
│  [Create FD] [Export Report] [Share Analysis]               │
└─────────────────────────────────────────────────────────────┘
```

---

## Option 2: Tabbed Interface
**Best for:** Clean separation, users who prefer focused views

```
┌─────────────────────────────────────────────────────────────┐
│  Results Panel                                               │
│  ─────────────────────────────────────────────────────────  │
│  [ Overview ] [ Analysis ] [ Charts ] [ Recommendations ]   │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  [Tab Content Area - changes based on selection]      │  │
│  │                                                       │  │
│  │  When "Analysis" tab selected:                        │  │
│  │  • Provider deep-dive details                         │  │
│  │  • Risk analysis                                      │  │
│  │  • Strategic recommendations                          │  │
│  │                                                       │  │
│  │  When "Charts" tab selected:                          │  │
│  │  • ECharts visualizations                             │  │
│  │  • Rate comparison graphs                             │  │
│  │  • Projection charts                                  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Option 3: Split-Screen Layout
**Best for:** Power users who want to compare analysis + charts simultaneously

```
┌─────────────────────────────────────────────────────────────┐
│  Results Panel                                               │
│  ─────────────────────────────────────────────────────────  │
│  ┌─────────────────────┬─────────────────────────────────┐  │
│  │  Analysis (Left)    │  Charts (Right)                 │  │
│  │  ─────────────────  │  ─────────────────────────────  │  │
│  │  ## Provider Details│  ┌───────────────────────────┐  │  │
│  │                     │  │  ECharts Visualization    │  │  │
│  │  ### HDFC Bank      │  │  [Interactive Bar Chart]  │  │  │
│  │  • Rate: 7.25%      │  │                           │  │  │
│  │  • Senior: 7.75%    │  │  [Toggle: Bar/Line/Pie]   │  │  │
│  │  • Pros: ...        │  │                           │  │  │
│  │  • Cons: ...        │  │  [Export Chart]           │  │  │
│  │                     │  └───────────────────────────┘  │  │
│  │  ### SBI            │                                 │  │
│  │  • Rate: 7.00%      │  ┌───────────────────────────┐  │  │
│  │  • Senior: 7.50%    │  │  Projection Chart         │  │  │
│  │  • Pros: ...        │  │  [Maturity over time]     │  │  │
│  │  • Cons: ...        │  └───────────────────────────┘  │  │
│  │                     │                                 │  │
│  │  ### Recommendations│                                 │  │
│  │  • Best for: ...    │                                 │  │
│  │  • Risk level: ...  │                                 │  │
│  └─────────────────────┴─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Recommendation Matrix

| Criteria              | Option 1 (Unified) | Option 2 (Tabs) | Option 3 (Split) |
|-----------------------|-------------------|-----------------|------------------|
| **Development Effort**| Low               | Medium          | High             |
| **Mobile Friendly**   | Excellent         | Good            | Poor             |
| **User Focus**        | Narrative flow    | Focused views   | Multi-tasking    |
| **Screen Real Estate**| Efficient         | Efficient       | Demanding        |
| **Learning Curve**    | None              | Minimal         | Moderate         |

---

## My Recommendation

**For Phase 1 integration, I recommend Option 1 (Unified Panel)** because:
1. **Lowest implementation effort** - minimal restructuring of existing template
2. **Natural narrative flow** - users read analysis and see charts in context
3. **Mobile-compatible** - stacks vertically on smaller screens
4. **Matches Streamlit reference** - your `streamlit_ref/` uses similar inline patterns

**Future enhancement:** Consider Option 2 (Tabs) if users request more focused views or if content grows too long.

---

## Next Steps

Please confirm your choice, and I'll:
1. Update CONTEXT.md with the decision
2. Create an ADR if this is a hard-to-reverse architectural decision
3. Move to the next grilling question