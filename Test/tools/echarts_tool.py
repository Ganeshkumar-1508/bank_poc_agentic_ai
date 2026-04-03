"""
Apache ECharts Configuration Builder Tool for CrewAI.

Builds valid ECharts option objects from structured data, suitable for
rendering with streamlit_echarts.st_echarts().

This tool is designed to be called by the data_visualizer_agent to produce
reliable chart configurations without relying on LLM-generated JSON.

Supported chart types:
    bar, line, pie, donut, gauge, scatter, radar

Usage (by the CrewAI agent):
    Pass a JSON string argument with the following fields:
    {
        "chart_type": "bar",          # required: bar|line|pie|donut|gauge|scatter|radar
        "title": "My Chart Title",    # required
        "x_labels": ["A", "B", "C"], # required for bar/line/scatter/radar
        "series": [                   # required
            {"name": "Series1", "data": [10, 20, 30]}
        ],
        "y_axis_name": "Value",       # optional
        "subtitle": "",               # optional
        "horizontal": false,          # optional (for bar charts)
        "stack": null                 # optional (for stacked bar/line)
    }

    For pie/donut charts, x_labels and series data are paired:
    x_labels = ["Bank1", "Bank2"]  →  series = [{"name": "Rates", "data": [7.5, 7.0]}]

    For gauge charts, series has a single data point:
    series = [{"name": "Score", "data": [85], "min": 0, "max": 100}]

Returns:
    A JSON string of the complete ECharts options dict, ready for
    st_echarts(options=json.loads(returned_string)).

    IMPORTANT: This tool deliberately avoids JsCode-dependent formatters
    (which cannot survive JSON round-trips) and uses ECharts template strings
    instead (e.g. "{b}: {c} ({d}%)") which work reliably in all contexts.
"""

import json
from typing import Any, Dict, List, Optional
from crewai.tools import BaseTool


# ──────────────────────────────────────────────────────────────────────────────
# Color palette (financial/professional theme)
# ──────────────────────────────────────────────────────────────────────────────
_FINANCIAL_COLORS = [
    "#3B82F6",  # blue
    "#EF4444",  # red
    "#10B981",  # emerald
    "#F59E0B",  # amber
    "#8B5CF6",  # violet
    "#EC4899",  # pink
    "#06B6D4",  # cyan
    "#F97316",  # orange
    "#14B8A6",  # teal
    "#6366F1",  # indigo
]


class EChartsBuilderTool(BaseTool):
    """
    CrewAI tool that programmatically builds valid Apache ECharts JSON
    configurations from structured input data.

    The agent provides a JSON string describing the desired chart, and the
    tool returns a complete ECharts options object as a JSON string.
    """

    name: str = "Apache ECharts Configuration Builder"
    description: str = (
        "Builds a valid Apache ECharts JSON configuration for rendering in "
        "Streamlit with st_echarts. Call this tool whenever you need to create "
        "a chart or visualization.\n\n"
        "Pass a single JSON string argument with these fields:\n"
        "  - chart_type (required): 'bar', 'line', 'pie', 'donut', 'gauge', "
        "'scatter', or 'radar'\n"
        "  - title (required): Chart title text\n"
        "  - subtitle (optional): Chart subtitle\n"
        "  - x_labels (required for bar/line/scatter/radar): JSON array of "
        "category names\n"
        "  - series (required): JSON array of series objects, each with:\n"
        "      - name (string): series name\n"
        "      - data (array of numbers): values for each category\n"
        "  - y_axis_name (optional): Y-axis label for bar/line charts\n"
        "  - horizontal (optional): true for horizontal bar charts\n"
        "  - stack (optional): string name for stacked bars/lines\n"
        "  - min / max (optional for gauge): min and max range values\n"
        "  - colors (optional): array of hex color strings\n\n"
        "Examples:\n"
        '  Bar chart: {"chart_type":"bar","title":"FD Rates","x_labels":'
        '["Bank1","Bank2"],"series":[{"name":"Rate","data":[7.5,7.0]}]}\n'
        '  Pie chart: {"chart_type":"pie","title":"Distribution","x_labels":'
        '["Bank1","Bank2","Bank3"],"series":[{"name":"Rate","data":[40,35,25]}]}\n'
        '  Gauge: {"chart_type":"gauge","title":"Risk Score","series":'
        '[{"name":"Score","data":[42],"min":0,"max":100}]}\n\n'
        "Returns a JSON string of the complete ECharts options object."
    )

    def _run(self, config_json: str) -> str:
        """
        Build ECharts options from a JSON string describing the desired chart.

        Parameters
        ----------
        config_json : str
            JSON string with chart configuration (see class docstring).

        Returns
        -------
        str
            JSON string of the complete ECharts options dict.
        """
        # ── Parse input ────────────────────────────────────────────────────
        try:
            config = json.loads(config_json.strip())
        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"Invalid JSON input to EChartsBuilderTool: {e}",
                "error_type": "JSON_PARSE_ERROR",
            })

        # ── Extract fields with defaults ───────────────────────────────────
        chart_type = str(config.get("chart_type", "bar")).lower().strip()
        title = str(config.get("title", "Chart"))
        subtitle = str(config.get("subtitle", ""))
        x_labels = config.get("x_labels", [])
        series = config.get("series", [])
        y_axis_name = str(config.get("y_axis_name", ""))
        horizontal = bool(config.get("horizontal", False))
        stack = config.get("stack", None)
        colors = config.get("colors", _FINANCIAL_COLORS)
        show_legend = bool(config.get("show_legend", True))
        width = config.get("width", None)
        height = config.get("height", None)

        # ── Validate required fields ───────────────────────────────────────
        if not series:
            return json.dumps({
                "error": "No series data provided. "
                         "Pass at least one series with name and data.",
                "error_type": "MISSING_DATA",
            })

        # ── Dispatch to chart-type builder ─────────────────────────────────
        builder_map = {
            "bar": self._build_cartesian,
            "line": self._build_cartesian,
            "scatter": self._build_cartesian,
            "pie": self._build_pie,
            "donut": self._build_pie,
            "gauge": self._build_gauge,
            "radar": self._build_radar,
        }
        builder = builder_map.get(chart_type, self._build_cartesian)

        options = builder(
            chart_type=chart_type,
            title=title,
            subtitle=subtitle,
            x_labels=x_labels,
            series=series,
            y_axis_name=y_axis_name,
            horizontal=horizontal,
            stack=stack,
            colors=colors,
            show_legend=show_legend,
        )

        # ── Return JSON string ─────────────────────────────────────────────
        return json.dumps(options, ensure_ascii=False)

    # ══════════════════════════════════════════════════════════════════════
    # CHART BUILDERS
    # ══════════════════════════════════════════════════════════════════════

    def _build_cartesian(
        self, *, chart_type, title, subtitle, x_labels, series,
        y_axis_name, horizontal, stack, colors, show_legend,
    ) -> Dict[str, Any]:
        """Build options for bar, line, and scatter charts."""
        is_scatter = chart_type == "scatter"
        effective_type = "scatter" if is_scatter else chart_type

        # Legend
        legend_cfg: Dict[str, Any] = {
            "data": [s.get("name", f"Series {i}") for i, s in enumerate(series)],
            "bottom": 0,
        }
        if not show_legend:
            legend_cfg = {"show": False}

        # Axes
        if horizontal:
            x_axis = {"type": "value"}
            if y_axis_name:
                x_axis["name"] = y_axis_name
            y_axis = {
                "type": "category",
                "data": list(x_labels),
                "axisLabel": {"rotate": 0, "interval": 0},
            }
        else:
            rotate = 30 if len(x_labels) > 6 else (15 if len(x_labels) > 3 else 0)
            x_axis = {
                "type": "category",
                "data": list(x_labels),
                "axisLabel": {
                    "rotate": rotate,
                    "interval": 0,
                    "fontSize": 11,
                },
            }
            y_axis = {"type": "value"}
            if y_axis_name:
                y_axis["name"] = y_axis_name

        # Title
        title_cfg: Dict[str, Any] = {
            "text": title,
            "left": "center",
            "textStyle": {"fontSize": 16, "fontWeight": "bold"},
        }
        if subtitle:
            title_cfg["subtext"] = subtitle

        # Series
        built_series = []
        for s in series:
            s_type = str(s.get("type", effective_type))
            entry: Dict[str, Any] = {
                "name": s.get("name", ""),
                "type": s_type,
                "data": s.get("data", []),
            }

            # Line-specific options
            if s_type == "line":
                entry["smooth"] = bool(s.get("smooth", True))
                if s.get("area_style"):
                    entry["areaStyle"] = {"opacity": 0.3}
                entry["lineStyle"] = {"width": 2}

            # Scatter-specific options
            if s_type == "scatter":
                entry["symbolSize"] = int(s.get("symbol_size", 10))

            # Stacking
            if stack is not None:
                entry["stack"] = stack

            # Label (show values on bars)
            if s.get("show_label"):
                entry["label"] = {"show": True, "position": "top"}

            # Custom item style
            if "itemStyle" in s:
                entry["itemStyle"] = s["itemStyle"]

            built_series.append(entry)

        return {
            "title": title_cfg,
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "shadow"} if effective_type == "bar" else {"type": "cross"},
            },
            "legend": legend_cfg,
            "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
            "xAxis": x_axis,
            "yAxis": y_axis,
            "series": built_series,
            "color": colors,
        }

    def _build_pie(
        self, *, chart_type, title, subtitle, x_labels, series,
        y_axis_name, horizontal, stack, colors, show_legend,
    ) -> Dict[str, Any]:
        """Build options for pie and donut charts."""
        is_donut = chart_type == "donut"
        pie_data: List[Dict[str, Any]] = []

        # Case 1: single series with parallel data, paired with x_labels
        if len(series) == 1 and isinstance(series[0].get("data"), list) and x_labels:
            for i, val in enumerate(series[0]["data"]):
                name = x_labels[i] if i < len(x_labels) else f"Item {i + 1}"
                pie_data.append({"name": str(name), "value": val})

        # Case 2: multiple series, each is a slice
        elif len(series) > 1:
            for s in series:
                val = s.get("data", 0)
                if isinstance(val, list):
                    val = val[0] if val else 0
                pie_data.append({"name": str(s.get("name", "")), "value": val})

        # Case 3: series already formatted as [{name, value}, ...]
        else:
            for s in series:
                if "value" in s and "name" in s:
                    pie_data.append({"name": str(s["name"]), "value": s["value"]})
                else:
                    name = s.get("name", "")
                    data = s.get("data", 0)
                    if isinstance(data, list):
                        data = data[0] if data else 0
                    pie_data.append({"name": str(name), "value": data})

        # Title
        title_cfg: Dict[str, Any] = {
            "text": title,
            "left": "center",
            "textStyle": {"fontSize": 16, "fontWeight": "bold"},
        }
        if subtitle:
            title_cfg["subtext"] = subtitle

        # Legend
        legend_cfg: Dict[str, Any] = {
            "type": "scroll",
            "orient": "vertical",
            "right": "5%",
            "top": "middle",
            "data": [d["name"] for d in pie_data],
        }
        if not show_legend:
            legend_cfg = {"show": False}

        radius = ["40%", "70%"] if is_donut else ["0%", "70%"]

        return {
            "title": title_cfg,
            "tooltip": {
                "trigger": "item",
                "formatter": "{a} <br/>{b}: {c} ({d}%)",
            },
            "legend": legend_cfg,
            "color": colors,
            "series": [{
                "name": title,
                "type": "pie",
                "radius": radius,
                "center": ["40%", "55%"],
                "data": pie_data,
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowOffsetX": 0,
                        "shadowColor": "rgba(0, 0, 0, 0.5)",
                    }
                },
                "label": {
                    "show": True,
                    "formatter": "{b}: {d}%",
                },
                "labelLine": {"show": True},
                "itemStyle": {
                    "borderRadius": 6 if is_donut else 0,
                    "borderColor": "#fff",
                    "borderWidth": 2 if is_donut else 0,
                },
            }],
        }

    def _build_gauge(
        self, *, chart_type, title, subtitle, x_labels, series,
        y_axis_name, horizontal, stack, colors, show_legend,
    ) -> Dict[str, Any]:
        """Build options for gauge charts."""
        # Extract value from first series
        value = 0
        min_val = 0
        max_val = 100
        name = title

        if series:
            s = series[0]
            data = s.get("data", [0])
            if isinstance(data, list):
                value = data[0] if data else 0
            else:
                value = data
            name = s.get("name", title)
            min_val = s.get("min", 0)
            max_val = s.get("max", 100)

        # Title
        title_cfg: Dict[str, Any] = {
            "text": title,
            "left": "center",
            "textStyle": {"fontSize": 16, "fontWeight": "bold"},
        }
        if subtitle:
            title_cfg["subtext"] = subtitle

        return {
            "title": title_cfg,
            "series": [{
                "type": "gauge",
                "min": min_val,
                "max": max_val,
                "splitNumber": 10,
                "axisLine": {
                    "lineStyle": {
                        "width": 15,
                        "color": [
                            [0.3, "#EF4444"],
                            [0.7, "#F59E0B"],
                            [1, "#10B981"],
                        ],
                    }
                },
                "pointer": {"itemStyle": {"color": "auto"}},
                "axisTick": {"distance": -15, "length": 6, "lineStyle": {"color": "#fff", "width": 1}},
                "splitLine": {"distance": -15, "length": 15, "lineStyle": {"color": "#fff", "width": 2}},
                "axisLabel": {"color": "inherit", "distance": 25, "fontSize": 12},
                "detail": {
                    "valueAnimation": True,
                    "formatter": "{value}",
                    "color": "inherit",
                    "fontSize": 20,
                },
                "data": [{"value": value, "name": name}],
            }],
        }

    def _build_radar(
        self, *, chart_type, title, subtitle, x_labels, series,
        y_axis_name, horizontal, stack, colors, show_legend,
    ) -> Dict[str, Any]:
        """Build options for radar charts."""
        if not x_labels:
            return {"error": "Radar charts require x_labels (indicator names)."}

        # Determine max value from data
        max_val = 100
        for s in series:
            data = s.get("data", [])
            if isinstance(data, list) and data:
                data_max = max(abs(v) for v in data if isinstance(v, (int, float)))
                if data_max > max_val:
                    max_val = data_max

        indicators = [{"name": str(lbl), "max": max_val} for lbl in x_labels]

        radar_series = []
        for s in series:
            radar_series.append({
                "value": s.get("data", []),
                "name": s.get("name", ""),
                "areaStyle": {"opacity": 0.2},
            })

        # Title
        title_cfg: Dict[str, Any] = {
            "text": title,
            "left": "center",
            "textStyle": {"fontSize": 16, "fontWeight": "bold"},
        }
        if subtitle:
            title_cfg["subtext"] = subtitle

        # Legend
        legend_cfg: Dict[str, Any] = {
            "data": [s.get("name", f"Series {i}") for i, s in enumerate(series)],
            "bottom": 0,
        }
        if not show_legend:
            legend_cfg = {"show": False}

        return {
            "title": title_cfg,
            "tooltip": {},
            "legend": legend_cfg,
            "color": colors,
            "radar": {
                "indicator": indicators,
                "center": ["50%", "55%"],
                "radius": "70%",
            },
            "series": [{
                "type": "radar",
                "data": radar_series,
            }],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton for import convenience
# ──────────────────────────────────────────────────────────────────────────────
echarts_builder_tool = EChartsBuilderTool()