"""
Test script for EChartsBuilderTool with FD comparison data.
Tests grouped bar charts for Risk vs Reward visualization.
"""

import json
import sys
import os

# Add the tools directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

# Import directly from the module file
from echarts_tool import EChartsBuilderTool

# Create tool instance
tool = EChartsBuilderTool()

# Test Case 1: Grouped Bar Chart - Risk Score vs Return (%) for FD Providers
print("=" * 60)
print("Test Case 1: Grouped Bar Chart - Risk vs Reward")
print("=" * 60)

config_1 = {
    "chart_type": "bar",
    "title": "FD Providers: Risk Score vs Annual Return",
    "subtitle": "Comparison of 5 Top Providers in India (2026)",
    "x_labels": ["HDFC Bank", "ICICI Bank", "SBI", "Bajaj Finance", "LIC Housing"],
    "series": [
        {"name": "Risk Score (1-10)", "data": [3, 4, 2, 6, 5]},
        {"name": "Return % (General)", "data": [7.05, 7.25, 7.10, 8.50, 8.25]},
        {"name": "Return % (Senior)", "data": [7.55, 7.75, 7.60, 9.00, 8.75]},
    ],
    "y_axis_name": "Value",
    "grouped": True,
    "colors": ["#EF4444", "#3B82F6", "#10B981"],
}

result_1 = tool._run(json.dumps(config_1))
print("Input Config:")
print(json.dumps(config_1, indent=2))
print("\nGenerated ECharts Options:")
parsed_1 = json.loads(result_1)
print(json.dumps(parsed_1, indent=2))

# Verify key elements
assert "series" in parsed_1, "Missing series in output"
assert len(parsed_1["series"]) == 3, "Expected 3 series"
assert (
    parsed_1["series"][0]["name"] == "Risk Score (1-10)"
), "First series name mismatch"
print("\n✓ Test Case 1 PASSED: Grouped bar chart generated successfully")

# Test Case 2: Simple Bar Chart - FD Rates Comparison
print("\n" + "=" * 60)
print("Test Case 2: Simple Bar Chart - FD Rates")
print("=" * 60)

config_2 = {
    "chart_type": "bar",
    "title": "Top 5 FD Rates for 12 Months",
    "subtitle": "General Citizen Rates (2026)",
    "x_labels": ["HDFC Bank", "ICICI Bank", "SBI", "Kotak Mahindra", "Axis Bank"],
    "series": [{"name": "Interest Rate (%)", "data": [7.05, 7.25, 7.10, 7.40, 7.30]}],
    "y_axis_name": "Interest Rate (%)",
}

result_2 = tool._run(json.dumps(config_2))
print("Input Config:")
print(json.dumps(config_2, indent=2))
print("\nGenerated ECharts Options:")
parsed_2 = json.loads(result_2)
print(json.dumps(parsed_2, indent=2))

assert len(parsed_2["series"]) == 1, "Expected 1 series"
assert parsed_2["series"][0]["data"] == [7.05, 7.25, 7.10, 7.40, 7.30], "Data mismatch"
print("\n✓ Test Case 2 PASSED: Simple bar chart generated successfully")

# Test Case 3: Scatter Chart - Risk vs Reward (Alternative Visualization)
print("\n" + "=" * 60)
print("Test Case 3: Scatter Chart - Risk vs Reward")
print("=" * 60)

config_3 = {
    "chart_type": "scatter",
    "title": "Risk vs Reward: FD Providers",
    "subtitle": "Risk Score (X) vs Annual Return % (Y)",
    "x_axis_name": "Risk Score (1-10)",
    "y_axis_name": "Annual Return (%)",
    "scatter_x_min": 1,
    "scatter_x_max": 10,
    "scatter_y_min": 6,
    "scatter_y_max": 10,
    "series": [
        {
            "name": "General Citizens",
            "data": [[3, 7.05], [4, 7.25], [2, 7.10], [6, 8.50], [5, 8.25]],
        },
        {
            "name": "Senior Citizens",
            "data": [[3, 7.55], [4, 7.75], [2, 7.60], [6, 9.00], [5, 8.75]],
        },
    ],
}

result_3 = tool._run(json.dumps(config_3))
print("Input Config:")
print(json.dumps(config_3, indent=2))
print("\nGenerated ECharts Options:")
parsed_3 = json.loads(result_3)
print(json.dumps(parsed_3, indent=2))

assert parsed_3["xAxis"]["type"] == "value", "X-axis should be value type for scatter"
assert parsed_3["yAxis"]["type"] == "value", "Y-axis should be value type for scatter"
print("\n✓ Test Case 3 PASSED: Scatter chart generated successfully")

# Test Case 4: Pie Chart - Market Share
print("\n" + "=" * 60)
print("Test Case 4: Pie Chart - Market Share")
print("=" * 60)

config_4 = {
    "chart_type": "pie",
    "title": "FD Market Share by Provider Type",
    "x_labels": ["Public Sector", "Private Sector", "NBFC", "Foreign Banks"],
    "series": [{"name": "Market Share (%)", "data": [35, 45, 15, 5]}],
}

result_4 = tool._run(json.dumps(config_4))
print("Input Config:")
print(json.dumps(config_4, indent=2))
print("\nGenerated ECharts Options:")
parsed_4 = json.loads(result_4)
print(json.dumps(parsed_4, indent=2))

assert parsed_4["series"][0]["type"] == "pie", "Series type should be pie"
print("\n✓ Test Case 4 PASSED: Pie chart generated successfully")

# Test Case 5: Gauge Chart - Overall Risk Score
print("\n" + "=" * 60)
print("Test Case 5: Gauge Chart - Overall Risk Score")
print("=" * 60)

config_5 = {
    "chart_type": "gauge",
    "title": "Portfolio Risk Score",
    "subtitle": "Average Risk Across All FD Holdings",
    "series": [{"name": "Risk Score", "data": [4.2], "min": 0, "max": 10}],
}

result_5 = tool._run(json.dumps(config_5))
print("Input Config:")
print(json.dumps(config_5, indent=2))
print("\nGenerated ECharts Options:")
parsed_5 = json.loads(result_5)
print(json.dumps(parsed_5, indent=2))

assert parsed_5["series"][0]["type"] == "gauge", "Series type should be gauge"
assert parsed_5["series"][0]["min"] == 0, "Gauge min should be 0"
assert parsed_5["series"][0]["max"] == 10, "Gauge max should be 10"
print("\n✓ Test Case 5 PASSED: Gauge chart generated successfully")

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
print("\nSummary:")
print("- Grouped bar charts for Risk vs Reward comparison: ✓")
print("- Simple bar charts for rate comparisons: ✓")
print("- Scatter charts for risk-reward scatter plots: ✓")
print("- Pie charts for market share: ✓")
print("- Gauge charts for risk scores: ✓")
print("\nThe EChartsBuilderTool is ready for use in FD comparison reports!")
