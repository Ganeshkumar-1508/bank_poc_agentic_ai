# tools/neo4j_tool.py
import random
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from datetime import datetime
from typing import Type, Dict, Any, Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from tools.config import (
    GRAPH_OUTPUT_DIR,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    _get_neo4j_graph,
    _get_native_neo4j_driver,
    get_neo4j_schema_context,
)

# ---------------------------------------------------------------------------
# Use shared Neo4j functions from tools.config
# ---------------------------------------------------------------------------

# Note: _get_neo4j_graph() is now imported from tools.config
# No need for duplicate singleton implementation


def _get_cypher_qa_chain(llm=None):
    global _cypher_qa_chain
    if _cypher_qa_chain is not None:
        return _cypher_qa_chain

    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain

    # Use the shared _get_neo4j_graph() from tools.config
    graph = _get_neo4j_graph()

    if graph is None:
        raise RuntimeError(
            "Neo4j connection not available. Check NEO4J_URI and credentials."
        )

    if llm is None:
        from tools.config import get_llm_3

        llm = get_llm_3()

    _cypher_qa_chain = GraphCypherQAChain.from_llm(
        llm=llm,
        graph=graph,
        verbose=True,
        allow_dangerous_requests=True,
        return_intermediate_steps=True,
    )
    return _cypher_qa_chain


def build_chain_with_llm(llm):
    """Inject project LLM into GraphCypherQAChain. Call from agents.py."""
    global _cypher_qa_chain
    _cypher_qa_chain = None
    return _get_cypher_qa_chain(llm=llm)


# ---------------------------------------------------------------------------
# Network graph image generator
# ---------------------------------------------------------------------------


def _generate_network_graph_from_results(records: list) -> Optional[str]:
    try:
        nodes: Dict[str, str] = {}
        node_labels: Dict[str, str] = {}
        edges: Dict[tuple, str] = {}

        def _process_value(value: Any) -> None:
            try:
                from neo4j.graph import Node, Relationship, Path
            except ImportError:
                return

            if isinstance(value, Node):
                nid = str(value.element_id)
                if nid not in nodes:
                    label = (
                        value.get("name")
                        or value.get("caption")
                        or value.get("title")
                        or (list(value.labels)[0] if value.labels else nid[:8])
                    )
                    nodes[nid] = str(label)[:40]
                    node_labels[nid] = (
                        list(value.labels)[0] if value.labels else "Unknown"
                    )
            elif isinstance(value, Relationship):
                src = str(value.start_node.element_id)
                tgt = str(value.end_node.element_id)
                for n in (value.start_node, value.end_node):
                    nid = str(n.element_id)
                    if nid not in nodes:
                        nodes[nid] = str(n.get("name") or n.get("caption") or nid[:8])[
                            :40
                        ]
                        node_labels[nid] = list(n.labels)[0] if n.labels else "Unknown"
                edge_key = (src, tgt, value.type)
                if edge_key not in edges:
                    edges[edge_key] = str(value.type)
            elif isinstance(value, Path):
                for n in value.nodes:
                    nid = str(n.element_id)
                    if nid not in nodes:
                        nodes[nid] = str(n.get("name") or n.get("caption") or nid[:8])[
                            :40
                        ]
                        node_labels[nid] = list(n.labels)[0] if n.labels else "Unknown"
                for r in value.relationships:
                    src = str(r.start_node.element_id)
                    tgt = str(r.end_node.element_id)
                    edge_key = (src, tgt, r.type)
                    if edge_key not in edges:
                        edges[edge_key] = str(r.type)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    _process_value(item)

        for record in records:
            if hasattr(record, "values"):
                for v in record.values():
                    _process_value(v)
            elif isinstance(record, dict):
                for v in record.values():
                    _process_value(v)

        if not nodes:
            return None

        MAX_NODES, MAX_EDGES = 150, 300

        if len(nodes) > MAX_NODES:
            import networkx as _nx

            _G_tmp = _nx.DiGraph()
            for s, t, _ in edges.keys():
                if s in nodes and t in nodes:
                    _G_tmp.add_edge(s, t)
            try:
                cycle_nodes = set()
                for cycle in _nx.simple_cycles(_G_tmp):
                    cycle_nodes.update(cycle)
            except Exception:
                cycle_nodes = set()
            deg = dict(_G_tmp.degree())
            priority = sorted(
                nodes.keys(), key=lambda n: (n not in cycle_nodes, -deg.get(n, 0))
            )
            kept_ids = set(priority[:MAX_NODES])
            nodes = {k: v for k, v in nodes.items() if k in kept_ids}
            node_labels = {k: v for k, v in node_labels.items() if k in kept_ids}
            edges = {
                k: v for k, v in edges.items() if k[0] in kept_ids and k[1] in kept_ids
            }

        if len(edges) > MAX_EDGES:
            edges = dict(list(edges.items())[:MAX_EDGES])

        G = nx.DiGraph()
        for nid, label in nodes.items():
            G.add_node(nid, label=label, node_type=node_labels.get(nid, "Unknown"))
        for (src, tgt, _), label in edges.items():
            if src in nodes and tgt in nodes:
                G.add_edge(src, tgt, label=label)

        if not G.nodes:
            return None

        plt.figure(figsize=(20, 14))
        plt.title("Entity Relationship Network", fontsize=16, fontweight="bold")

        try:
            pos = nx.kamada_kawai_layout(G)
        except Exception:
            pos = nx.spring_layout(G, seed=42, k=2.5)

        TYPE_COLORS = {
            "Person": "#4CAF50",
            "Company": "#2196F3",
            "Account": "#FF9800",
            "Transaction": "#9C27B0",
            "Unknown": "#607D8B",
        }
        node_colors = [
            TYPE_COLORS.get(G.nodes[n].get("node_type", "Unknown"), "#607D8B")
            for n in G.nodes()
        ]
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=800, alpha=0.9)
        nx.draw_networkx_edges(
            G,
            pos,
            edge_color="#555555",
            arrows=True,
            arrowsize=20,
            width=1.5,
            alpha=0.7,
            connectionstyle="arc3,rad=0.1",
        )
        nx.draw_networkx_edge_labels(
            G,
            pos,
            edge_labels={(u, v): d.get("label", "") for u, v, d in G.edges(data=True)},
            font_size=7,
        )
        nx.draw_networkx_labels(
            G,
            pos,
            labels={n: G.nodes[n].get("label", str(n)[:20]) for n in G.nodes()},
            font_size=9,
        )

        GRAPH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}.png"
        filepath = GRAPH_OUTPUT_DIR / filename
        plt.savefig(filepath, format="png", dpi=150, bbox_inches="tight")
        plt.close()
        return str(filepath.resolve())

    except Exception as e:
        print(f"Error generating graph: {e}")
        return None


# ---------------------------------------------------------------------------
# Tool 1: Neo4jQueryTool — raw Cypher execution + graph image
# ---------------------------------------------------------------------------


class CypherQueryInput(BaseModel):
    query: str = Field(..., description="A valid Cypher query string.")


class Neo4jQueryTool(BaseTool):
    """Executes a Cypher query against Neo4j and generates a network graph image."""

    name: str = "Neo4j Graph Query"
    description: str = (
        "Executes a Cypher query against the Neo4j database to map client networks. "
        "Returns a summary of nodes/relationships and a GRAPH_IMAGE_PATH for the rendered graph."
    )
    args_schema: Type[BaseModel] = CypherQueryInput

    def _run(self, query: str) -> str:
        driver = _get_native_neo4j_driver()
        if not driver:
            g = _get_neo4j_graph()
            if not g:
                return "Error: Neo4j is not reachable. Check NEO4J_URI / credentials in .env."
            return "Error: Native neo4j driver unavailable. Install 'neo4j' package."

        try:
            records = []
            with driver.session() as session:
                for record in session.run(query):
                    records.append(record)

            if not records:
                schema_hint = ""
                try:
                    schema_ctx = get_neo4j_schema_context()
                    if schema_ctx and "not available" not in schema_ctx:
                        schema_hint = "\n\nNEO4J_SCHEMA:\n" + schema_ctx
                except Exception:
                    pass
                return (
                    "Query executed but returned no results. Check Cypher for typos."
                    + schema_hint
                )

            image_path = _generate_network_graph_from_results(records)

            node_count = rel_count = 0
            try:
                from neo4j.graph import Node, Relationship, Path

                for record in records:
                    for val in record.values():
                        if isinstance(val, Node):
                            node_count += 1
                        elif isinstance(val, Relationship):
                            rel_count += 1
                        elif isinstance(val, Path):
                            node_count += len(list(val.nodes))
                            rel_count += len(list(val.relationships))
                        elif isinstance(val, (list, tuple)):
                            for item in val:
                                if isinstance(item, Node):
                                    node_count += 1
                                elif isinstance(item, Relationship):
                                    rel_count += 1
            except ImportError:
                pass

            sample_lines = []
            for rec in records[:3]:
                try:
                    sample_lines.append(str(dict(rec)))
                except Exception:
                    sample_lines.append(str(rec))

            return "\n".join(
                [
                    "Query executed successfully.",
                    f"Found approximately {node_count} nodes and {rel_count} relationships.",
                    (
                        f"GRAPH_IMAGE_PATH: {image_path}"
                        if image_path
                        else "GRAPH_IMAGE_PATH: NONE"
                    ),
                    "---",
                    "Sample Data (first 3 records):",
                ]
                + sample_lines
            )

        except Exception as e:
            schema_hint = ""
            try:
                g = _get_neo4j_graph()
                if g:
                    schema_hint = "\n\nNEO4J_SCHEMA:\n" + (
                        getattr(g, "schema", None)
                        or get_neo4j_schema_context()
                        or "Schema unavailable."
                    )
            except Exception:
                pass
            return f"Neo4j Query Error: {str(e)}{schema_hint}"


# ---------------------------------------------------------------------------
# Tool 2: Neo4jSchemaInspectorTool — live schema introspection
# ---------------------------------------------------------------------------


class SchemaInspectorInput(BaseModel):
    refresh: bool = Field(
        default=False, description="Force a live schema refresh from Neo4j."
    )


class Neo4jSchemaInspectorTool(BaseTool):
    """Returns the live Neo4j graph schema (node labels, relationship types, property keys)."""

    name: str = "Neo4j Schema Inspector"
    description: str = (
        "Returns the current Neo4j graph schema: node labels, relationship types, and property keys. "
        "Call before writing Cypher to ensure correct syntax. Set refresh=True to force a reload."
    )
    args_schema: Type[BaseModel] = SchemaInspectorInput

    def _run(self, refresh: bool = False) -> str:
        try:
            graph = _get_neo4j_graph_lc()
            if refresh:
                graph.refresh_schema()
            schema = graph.schema
            return (
                f"NEO4J_SCHEMA:\n{schema}"
                if schema
                else "NEO4J_SCHEMA: Empty — database may have no data."
            )
        except Exception as e:
            return f"NEO4J_SCHEMA_ERROR: {e}"


# ---------------------------------------------------------------------------
# Tool 3: GraphCypherQATool — natural-language → Cypher → answer
# ---------------------------------------------------------------------------


class CypherQAInput(BaseModel):
    question: str = Field(
        ...,
        description=(
            "A natural-language question about the graph, e.g. "
            "'Find all companies connected to John Doe within 2 hops'."
        ),
    )


# ---------------------------------------------------------------------------
# Tool 4: Neo4jNameSearchTool — direct name search (no schema introspection)
# ---------------------------------------------------------------------------


class NameSearchInput(BaseModel):
    first_name: str = Field(..., description="Entity first name (e.g. 'Alaa')")
    last_name: str = Field(..., description="Entity last name (e.g. 'Mubarak')")
    max_hops: int = Field(
        default=4, description="Maximum relationship hops for network expansion (1-4)"
    )
    limit_nodes: int = Field(
        default=20, description="Max starting nodes to match in Phase 1"
    )
    limit_results: int = Field(
        default=50, description="Max total results (p, r, connected) in Phase 2"
    )


class Neo4jNameSearchTool(BaseTool):
    """
    Searches the Neo4j graph for an entity by first_name and last_name.
    Builds and executes a parameterized Cypher query internally — NO schema
    introspection, NO intermediate Cypher generation step.

    Query pattern:
      Phase 1 — multi-label name search across Officer/Entity/Intermediary/Other
        with variations: 'first last', 'last, first', 'last first', original_name,
        translit_name, and standalone first AND last.
      Phase 2 — expand 1..max_hops to find the full connected network.
    """

    name: str = "Neo4j Entity Name Search"
    description: str = (
        "Searches the Neo4j graph for an entity by first_name and last_name. "
        "Builds and executes a parameterized Cypher query internally — no schema reading required. "
        "Searches across Officer, Entity, Intermediary, Other labels with name variations. "
        "Returns nodes, relationships, GRAPH_IMAGE_PATH, and a network summary. "
        "Input: first_name, last_name (required); max_hops, limit_nodes, limit_results (optional)."
    )
    args_schema: Type[BaseModel] = NameSearchInput

    # Cypher query template — uses Neo4j $parameters for name values
    # (hop count and limits are safe to interpolate since they are validated ints)
    _CYPHER_TEMPLATE: str = """
// Phase 1: Identify the starting node based on name variations
MATCH (p)
WHERE any(label IN labels(p) WHERE label IN ['Officer','Entity','Intermediary','Other'])
  AND (
    toLower(p.name) CONTAINS toLower($full_name)
    OR toLower(p.name) CONTAINS toLower($last_comma_first)
    OR toLower(p.name) CONTAINS toLower($last_first)
    OR toLower(p.original_name) CONTAINS toLower($full_name)
    OR toLower(p.translit_name) CONTAINS toLower($full_name)
    OR (toLower(p.name) CONTAINS toLower($full_name))
  )
WITH p LIMIT {limit_nodes}

// Phase 2: Expand the network to find related entities
MATCH (p)-[r*1..{max_hops}]-(connected)
RETURN p, r, connected
LIMIT {limit_results}
"""

    def _run(
        self,
        first_name: str,
        last_name: str,
        max_hops: int = 4,
        limit_nodes: int = 20,
        limit_results: int = 50,
    ) -> str:
        driver = _get_native_neo4j_driver()
        if not driver:
            g = _get_neo4j_graph()
            if not g:
                return "Error: Neo4j is not reachable. Check NEO4J_URI / credentials in .env."
            return "Error: Native neo4j driver unavailable. Install 'neo4j' package."

        # Clamp hop range to valid Cypher bounds
        max_hops = max(1, min(int(max_hops), 6))
        limit_nodes = max(1, min(int(limit_nodes), 100))
        limit_results = max(1, min(int(limit_results), 200))

        first_name = first_name.strip()
        last_name = last_name.strip()
        if not first_name or not last_name:
            return "Error: both first_name and last_name must be non-empty."

        full_name = f"{first_name} {last_name}"
        last_comma_first = f"{last_name}, {first_name}"
        last_first = f"{last_name} {first_name}"

        query = self._CYPHER_TEMPLATE.format(
            max_hops=max_hops,
            limit_nodes=limit_nodes,
            limit_results=limit_results,
        )

        params = {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "last_comma_first": last_comma_first,
            "last_first": last_first,
        }

        try:
            records = []
            with driver.session() as session:
                for record in session.run(query, params):
                    records.append(record)

            if not records:
                return (
                    f"No exact match for '{full_name}' in ICIJ Offshore Leaks database. "
                    f"Checked name variations: '{full_name}', '{last_comma_first}', '{last_first}', "
                    f"original_name, translit_name. The full name must appear together in the entity name."
                )

            image_path = _generate_network_graph_from_results(records)

            # Count nodes and relationships
            node_count = rel_count = 0
            try:
                from neo4j.graph import Node, Relationship, Path

                for record in records:
                    for val in record.values():
                        if isinstance(val, Node):
                            node_count += 1
                        elif isinstance(val, Relationship):
                            rel_count += 1
                        elif isinstance(val, Path):
                            node_count += len(list(val.nodes))
                            rel_count += len(list(val.relationships))
                        elif isinstance(val, (list, tuple)):
                            for item in val:
                                if isinstance(item, Node):
                                    node_count += 1
                                elif isinstance(item, Relationship):
                                    rel_count += 1
            except ImportError:
                pass

            sample_lines = []
            for rec in records[:3]:
                try:
                    sample_lines.append(str(dict(rec)))
                except Exception:
                    sample_lines.append(str(rec))

            return "\n".join(
                [
                    f"Name search for: '{full_name}' (first='{first_name}', last='{last_name}')",
                    "Query executed successfully (no schema introspection — direct parameterized Cypher).",
                    f"Found approximately {node_count} nodes and {rel_count} relationships.",
                    (
                        f"GRAPH_IMAGE_PATH: {image_path}"
                        if image_path
                        else "GRAPH_IMAGE_PATH: NONE"
                    ),
                    "---",
                    "Sample Data (first 3 records):",
                ]
                + sample_lines
            )

        except Exception as e:
            return f"Neo4j Name Search Error: {str(e)}"


# ---------------------------------------------------------------------------
# Tool 3: GraphCypherQATool — natural-language → Cypher → answer
# ---------------------------------------------------------------------------


class GraphCypherQATool(BaseTool):
    """
    Natural-language → Cypher → answer using LangChain's GraphCypherQAChain.
    Automatically generates and executes Cypher from a plain-English question.
    """

    name: str = "Neo4j Graph Cypher QA"
    description: str = (
        "Answers natural-language questions about the Neo4j graph by auto-generating and executing Cypher. "
        "Use for: client network mapping, entity relationship discovery, UBO tracing. "
        "Input: a plain English question. Returns a natural-language answer plus the Cypher executed."
    )
    args_schema: Type[BaseModel] = CypherQAInput
    _chain: object = PrivateAttr(default=None)

    def __init__(self, chain=None, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_chain", chain)

    def _run(self, question: str) -> str:
        try:
            chain = object.__getattribute__(self, "_chain") or _get_cypher_qa_chain()
            result = chain.invoke({"query": question})
            answer = result.get("result", "No answer returned.")
            intermediate = result.get("intermediate_steps", [])
            cypher_used = ""
            if intermediate:
                first_step = intermediate[0] if isinstance(intermediate, list) else {}
                cypher_used = first_step.get("query", "")
            return answer + (
                f"\n\nCYPHER_EXECUTED:\n{cypher_used}" if cypher_used else ""
            )
        except Exception as e:
            return f"NEO4J_QA_ERROR: {e}"


# Module-level singletons
neo4j_schema_tool = Neo4jSchemaInspectorTool()
graph_cypher_qa_tool = GraphCypherQATool()
neo4j_name_search_tool = Neo4jNameSearchTool()
