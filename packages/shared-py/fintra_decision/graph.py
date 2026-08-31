"""The Enterprise State Graph — a pure, domain-neutral relationship model.

SentriAI ultimately needs to understand how people, agents, service identities,
apps, APIs, cloud resources, data, vendors, money, controls and processes depend
on each other — so it can reason about the *consequence* of a machine action, not
just record that it happened.

This module is the neutral engine: typed **Node**s and directed, typed, weighted
**Edge**s, with deterministic traversal (downstream/upstream/path). It is pure
(zero deps) and holds AWS identity graphs and Fintra money-flow graphs as two
instances of the same shape — the domain seeds live in adapters, not here.

Determinism: neighbours are returned in sorted order and BFS is level-ordered, so
the same graph + query always yields the same result (safe for cached workflows).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .contract import Certainty

# Canonical relation vocabulary (extend per domain, but prefer reuse).
RELATIONS = {
    "owns", "accesses", "depends_on", "approves", "pays", "triggers",
    "controls", "reconciles", "assumes_role", "attached_to", "grants",
    "routes_to", "funds", "member_of", "reads", "writes",
}


@dataclass(frozen=True)
class Node:
    id: str
    kind: str                       # human | agent | service | role | policy |
                                    # resource | vendor | bank_account | invoice |
                                    # payment | journal | control | data | ...
    attrs: Tuple[Tuple[str, Any], ...] = ()   # frozen for hashability

    @staticmethod
    def of(id: str, kind: str, **attrs: Any) -> "Node":
        return Node(id=id, kind=kind, attrs=tuple(sorted(attrs.items())))

    @property
    def attr_dict(self) -> Dict[str, Any]:
        return dict(self.attrs)


@dataclass
class Edge:
    src: str
    dst: str
    relation: str
    weight: float = 1.0             # coupling strength 0..1 (impact propagation)
    certainty: Certainty = Certainty.KNOWN


@dataclass
class Impact:
    node_id: str
    hops: int
    path_weight: float              # product of edge weights along the shortest path
    certainty: Certainty            # weakest certainty along the path


# certainty ordering (weakest wins along a path)
_CERT_RANK = {Certainty.KNOWN: 3, Certainty.INFERRED: 2,
              Certainty.SIMULATED: 1, Certainty.UNKNOWN: 0}


def _weakest(a: Certainty, b: Certainty) -> Certainty:
    return a if _CERT_RANK[a] <= _CERT_RANK[b] else b


class StateGraph:
    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._out: Dict[str, List[Edge]] = {}
        self._in: Dict[str, List[Edge]] = {}

    # ── build ────────────────────────────────────────────────────────────────
    def add_node(self, node: Node) -> Node:
        self._nodes[node.id] = node
        self._out.setdefault(node.id, [])
        self._in.setdefault(node.id, [])
        return node

    def add_edge(self, src: str, dst: str, relation: str, *,
                 weight: float = 1.0, certainty: Certainty = Certainty.KNOWN) -> Edge:
        for nid in (src, dst):
            if nid not in self._nodes:
                self.add_node(Node.of(nid, "unknown"))
        e = Edge(src=src, dst=dst, relation=relation, weight=weight, certainty=certainty)
        self._out[src].append(e)
        self._in[dst].append(e)
        return e

    # ── query ────────────────────────────────────────────────────────────────
    def node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def nodes(self) -> List[Node]:
        return [self._nodes[k] for k in sorted(self._nodes)]

    def neighbors(self, node_id: str, *, relation: Optional[str] = None,
                  direction: str = "out") -> List[Edge]:
        edges = list(self._out.get(node_id, [])) if direction in ("out", "both") else []
        if direction in ("in", "both"):
            edges += list(self._in.get(node_id, []))
        if relation:
            edges = [e for e in edges if e.relation == relation]
        return sorted(edges, key=lambda e: (e.relation, e.dst, e.src))

    def downstream(self, node_id: str, *, max_hops: int = 4,
                   relations: Optional[Iterable[str]] = None,
                   direction: str = "out") -> List[Impact]:
        """Level-ordered BFS tracking hop distance, path weight (product of edge
        weights) and the weakest certainty on the path. `direction="out"` follows
        outgoing edges; `"in"` follows incoming (the *dependents*). Deterministic."""
        rel_filter = set(relations) if relations else None
        step = "out" if direction == "out" else "in"
        best: Dict[str, Impact] = {}
        start = Impact(node_id=node_id, hops=0, path_weight=1.0, certainty=Certainty.KNOWN)
        q: deque = deque([start])
        while q:
            cur = q.popleft()
            if cur.hops >= max_hops:
                continue
            for e in self.neighbors(cur.node_id, direction=step):
                if rel_filter and e.relation not in rel_filter:
                    continue
                other = e.dst if step == "out" else e.src
                nxt = Impact(
                    node_id=other,
                    hops=cur.hops + 1,
                    path_weight=round(cur.path_weight * e.weight, 6),
                    certainty=_weakest(cur.certainty, e.certainty),
                )
                prev = best.get(other)
                # prefer the shorter, then stronger-weighted path
                if prev is None or (nxt.hops, -nxt.path_weight) < (prev.hops, -prev.path_weight):
                    best[other] = nxt
                    q.append(nxt)
        return sorted(best.values(), key=lambda i: (i.hops, -i.path_weight, i.node_id))

    def dependents(self, node_id: str, *, max_hops: int = 4,
                   relations: Optional[Iterable[str]] = None) -> List[Impact]:
        """What could changing this node affect? = everything that (transitively)
        depends on / references it — BFS over INCOMING edges. This is the traversal
        the Consequence engine uses (dependency edges point dependent→dependency)."""
        return self.downstream(node_id, max_hops=max_hops, relations=relations, direction="in")

    def path(self, src: str, dst: str, *, max_hops: int = 6) -> Optional[List[str]]:
        """A shortest relation path src→dst (node ids), or None. Deterministic BFS."""
        if src == dst:
            return [src]
        q: deque = deque([(src, [src])])
        seen = {src}
        while q:
            cur, trail = q.popleft()
            if len(trail) - 1 >= max_hops:
                continue
            for e in self.neighbors(cur, direction="out"):
                if e.dst in seen:
                    continue
                if e.dst == dst:
                    return trail + [dst]
                seen.add(e.dst)
                q.append((e.dst, trail + [e.dst]))
        return None

    def summary(self) -> Dict[str, Any]:
        kinds: Dict[str, int] = {}
        for n in self._nodes.values():
            kinds[n.kind] = kinds.get(n.kind, 0) + 1
        edge_count = sum(len(v) for v in self._out.values())
        return {"nodes": len(self._nodes), "edges": edge_count, "by_kind": kinds}
