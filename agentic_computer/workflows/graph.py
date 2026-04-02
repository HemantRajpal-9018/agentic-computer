"""DAG-based task graph for agentic-computer workflows.

Provides :class:`TaskGraph`, a directed acyclic graph (DAG) of executable
tasks with dependency tracking, topological ordering, cycle detection, and
serialisation.  Uses `networkx <https://networkx.org>`_ for all core graph
operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Node:
    """A single task node in the graph.

    Attributes:
        id: Unique identifier within the graph.
        label: Human-readable display name.
        data: Arbitrary payload attached to the node (tool name, params, etc.).
        dependencies: IDs of nodes that this node depends on.
    """

    id: str
    label: str
    data: dict[str, Any] = field(default_factory=dict)
    dependencies: set[str] = field(default_factory=set)


@dataclass
class Edge:
    """A directed dependency edge from *source* to *target*.

    Semantics: *target* depends on *source* — i.e. *source* must complete
    before *target* may start.

    Attributes:
        source: ID of the upstream node.
        target: ID of the downstream node.
        label: Optional annotation describing the relationship.
    """

    source: str
    target: str
    label: str = ""


# ---------------------------------------------------------------------------
# Task graph
# ---------------------------------------------------------------------------


class TaskGraph:
    """Directed acyclic graph of tasks with dependency-aware ordering.

    Internally backed by a :class:`networkx.DiGraph`.  Nodes carry ``label``
    and ``data`` attributes; edges carry an optional ``label``.

    Example::

        graph = TaskGraph()
        graph.add_node("fetch", "Fetch data", data={"url": "https://example.com"})
        graph.add_node("parse", "Parse data", dependencies={"fetch"})
        graph.add_edge("fetch", "parse", "raw data")
        layers = graph.get_execution_order()
        # [['fetch'], ['parse']]
    """

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(
        self,
        id: str,
        label: str,
        data: dict[str, Any] | None = None,
        dependencies: set[str] | None = None,
    ) -> Node:
        """Add a task node to the graph.

        If *dependencies* are provided, edges are automatically created from
        each dependency to this node.

        Args:
            id: Unique node identifier.
            label: Human-readable display name.
            data: Arbitrary metadata for the node.
            dependencies: IDs of nodes this node depends on.  Edges are
                created automatically.

        Returns:
            The newly created :class:`Node`.

        Raises:
            ValueError: If a node with the same *id* already exists.
        """
        if id in self._graph:
            raise ValueError(f"Node '{id}' already exists in the graph")

        node_data = data or {}
        deps = dependencies or set()

        self._graph.add_node(id, label=label, data=node_data, dependencies=deps)

        # Create edges from each dependency to this node.
        for dep_id in deps:
            if dep_id not in self._graph:
                # Add a placeholder so the edge is valid.  The caller must
                # fill in the real node later; ``validate()`` will flag it.
                self._graph.add_node(dep_id, label=dep_id, data={}, dependencies=set())
                logger.warning(
                    "Dependency '%s' for node '%s' does not exist yet — "
                    "created placeholder.",
                    dep_id,
                    id,
                )
            self._graph.add_edge(dep_id, id)

        node = Node(id=id, label=label, data=node_data, dependencies=deps)
        logger.debug("Added node '%s' (%s) with deps %s", id, label, deps)
        return node

    def remove_node(self, id: str) -> None:
        """Remove a node and all its incident edges from the graph.

        Args:
            id: Identifier of the node to remove.

        Raises:
            KeyError: If no node with *id* exists.
        """
        if id not in self._graph:
            raise KeyError(f"Node '{id}' not found in the graph")

        self._graph.remove_node(id)

        # Clean up stale dependency references in remaining nodes.
        for node_id in self._graph.nodes:
            deps: set[str] = self._graph.nodes[node_id].get("dependencies", set())
            deps.discard(id)

        logger.debug("Removed node '%s'", id)

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(
        self,
        source: str,
        target: str,
        label: str = "",
    ) -> Edge:
        """Add a directed edge from *source* to *target*.

        Both *source* and *target* must already exist in the graph.

        Args:
            source: ID of the upstream node.
            target: ID of the downstream node.
            label: Optional annotation.

        Returns:
            The newly created :class:`Edge`.

        Raises:
            KeyError: If *source* or *target* does not exist.
        """
        for node_id in (source, target):
            if node_id not in self._graph:
                raise KeyError(f"Node '{node_id}' not found in the graph")

        self._graph.add_edge(source, target, label=label)

        # Keep the target's dependency set consistent.
        deps: set[str] = self._graph.nodes[target].get("dependencies", set())
        deps.add(source)
        self._graph.nodes[target]["dependencies"] = deps

        logger.debug("Added edge '%s' -> '%s' (%s)", source, target, label)
        return Edge(source=source, target=target, label=label)

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_execution_order(self) -> list[list[str]]:
        """Return a topological ordering of node IDs grouped into layers.

        Each layer contains nodes whose dependencies are all in previous
        layers, so nodes within a layer can be executed in parallel.

        Returns:
            A list of layers, each layer being a list of node IDs.

        Raises:
            ValueError: If the graph contains a cycle.
        """
        if not nx.is_directed_acyclic_graph(self._graph):
            cycles = list(nx.simple_cycles(self._graph))
            raise ValueError(
                f"Graph contains {len(cycles)} cycle(s); "
                f"cannot determine execution order. First cycle: {cycles[0]}"
            )

        # Build layers via topological generations (available since networkx 2.6).
        return [sorted(layer) for layer in nx.topological_generations(self._graph)]

    def get_dependencies(self, node_id: str) -> set[str]:
        """Return the IDs of all direct predecessors (dependencies) of *node_id*.

        Args:
            node_id: The node to query.

        Returns:
            Set of predecessor node IDs.

        Raises:
            KeyError: If *node_id* is not in the graph.
        """
        if node_id not in self._graph:
            raise KeyError(f"Node '{node_id}' not found in the graph")
        return set(self._graph.predecessors(node_id))

    def get_dependents(self, node_id: str) -> set[str]:
        """Return the IDs of all direct successors (dependents) of *node_id*.

        Args:
            node_id: The node to query.

        Returns:
            Set of successor node IDs.

        Raises:
            KeyError: If *node_id* is not in the graph.
        """
        if node_id not in self._graph:
            raise KeyError(f"Node '{node_id}' not found in the graph")
        return set(self._graph.successors(node_id))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Check the graph for structural problems and return a list of
        human-readable issue descriptions.

        Checks performed:

        * **Cycles** — the graph must be a DAG.
        * **Missing dependencies** — every ID in a node's ``dependencies``
          set must correspond to an actual node.
        * **Orphaned edges** — edges whose source or target is absent.
        * **Empty graph** — a graph with no nodes is considered an issue.

        Returns:
            A (possibly empty) list of issue descriptions.  An empty list
            means the graph is valid.
        """
        issues: list[str] = []

        if self._graph.number_of_nodes() == 0:
            issues.append("Graph is empty — no nodes defined.")
            return issues

        # Cycle detection.
        if not nx.is_directed_acyclic_graph(self._graph):
            cycles = list(nx.simple_cycles(self._graph))
            for cycle in cycles:
                issues.append(f"Cycle detected: {' -> '.join(cycle + [cycle[0]])}")

        # Missing dependency references.
        all_ids = set(self._graph.nodes)
        for node_id in self._graph.nodes:
            declared_deps: set[str] = self._graph.nodes[node_id].get(
                "dependencies", set()
            )
            missing = declared_deps - all_ids
            for dep in sorted(missing):
                issues.append(
                    f"Node '{node_id}' declares dependency '{dep}' which does "
                    f"not exist."
                )

        # Check that declared dependencies match actual incoming edges.
        for node_id in self._graph.nodes:
            declared_deps = self._graph.nodes[node_id].get("dependencies", set())
            actual_preds = set(self._graph.predecessors(node_id))
            missing_edges = declared_deps - actual_preds
            for dep in sorted(missing_edges):
                if dep in all_ids:
                    issues.append(
                        f"Node '{node_id}' declares dependency '{dep}' but no "
                        f"edge exists from '{dep}' to '{node_id}'."
                    )

        return issues

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the graph to a plain dictionary.

        The output format is::

            {
                "nodes": [
                    {
                        "id": "fetch",
                        "label": "Fetch data",
                        "data": {...},
                        "dependencies": ["other_id"]
                    },
                    ...
                ],
                "edges": [
                    {"source": "fetch", "target": "parse", "label": "raw data"},
                    ...
                ]
            }

        Returns:
            A JSON-serialisable dictionary.
        """
        nodes: list[dict[str, Any]] = []
        for node_id, attrs in self._graph.nodes(data=True):
            nodes.append(
                {
                    "id": node_id,
                    "label": attrs.get("label", node_id),
                    "data": attrs.get("data", {}),
                    "dependencies": sorted(attrs.get("dependencies", set())),
                }
            )

        edges: list[dict[str, Any]] = []
        for src, tgt, attrs in self._graph.edges(data=True):
            edges.append(
                {
                    "source": src,
                    "target": tgt,
                    "label": attrs.get("label", ""),
                }
            )

        return {"nodes": nodes, "edges": edges}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskGraph:
        """Reconstruct a :class:`TaskGraph` from a dictionary produced by
        :meth:`to_dict`.

        Args:
            data: Dictionary with ``"nodes"`` and ``"edges"`` keys.

        Returns:
            A new :class:`TaskGraph` instance.

        Raises:
            ValueError: If required keys are missing.
        """
        if "nodes" not in data:
            raise ValueError("Missing 'nodes' key in graph data")

        graph = cls()

        # First pass: add all nodes without dependency edges so that IDs
        # exist before we create edges.
        for node_data in data["nodes"]:
            node_id = node_data["id"]
            graph._graph.add_node(
                node_id,
                label=node_data.get("label", node_id),
                data=node_data.get("data", {}),
                dependencies=set(node_data.get("dependencies", [])),
            )

        # Second pass: add edges from declared dependencies.
        for node_data in data["nodes"]:
            node_id = node_data["id"]
            for dep in node_data.get("dependencies", []):
                if dep in graph._graph:
                    graph._graph.add_edge(dep, node_id)

        # Add any extra explicit edges from the "edges" list.
        for edge_data in data.get("edges", []):
            src = edge_data["source"]
            tgt = edge_data["target"]
            if src in graph._graph and tgt in graph._graph:
                graph._graph.add_edge(src, tgt, label=edge_data.get("label", ""))
                # Ensure dependency set stays consistent.
                deps: set[str] = graph._graph.nodes[tgt].get("dependencies", set())
                deps.add(src)
                graph._graph.nodes[tgt]["dependencies"] = deps

        return graph

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the graph."""
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """Return the number of edges in the graph."""
        return self._graph.number_of_edges()

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._graph

    def __len__(self) -> int:
        return self._graph.number_of_nodes()

    def __repr__(self) -> str:
        return (
            f"TaskGraph(nodes={self._graph.number_of_nodes()}, "
            f"edges={self._graph.number_of_edges()})"
        )
