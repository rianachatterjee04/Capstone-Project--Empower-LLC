"""
HR → Company Brain publisher (fail-open, fire-and-forget). Mirrors the accounting
publisher: records HR facts (hires, etc.) into the shared knowledge graph + event
bus so the brain understands the workforce alongside finance & compliance.

Env: BRAIN_API_URL, INTERNAL_BRAIN_SECRET. No-op when unset.
"""
from __future__ import annotations
import os
import threading

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

BRAIN_URL = os.getenv("BRAIN_API_URL", "")
SECRET = os.getenv("INTERNAL_BRAIN_SECRET") or os.getenv("INTERNAL_AI_SHARED_SECRET", "dev-internal-secret")


def ingest(org_id: str, *, nodes=None, edges=None, event=None) -> None:
    if not BRAIN_URL or not org_id or httpx is None:
        return

    def _go():
        try:
            httpx.post(
                BRAIN_URL.rstrip("/") + "/ingest",
                json={"nodes": nodes or [], "edges": edges or [], "event": event},
                headers={"Authorization": f"Bearer {SECRET}", "X-Org-Id": str(org_id)},
                timeout=3,
            )
        except Exception:
            pass

    threading.Thread(target=_go, daemon=True).start()


def record_hire(org_id: str, *, employee_id: str, name: str = "", department: str = "",
                manager_id: str = "") -> None:
    nodes = [{"kind": "employee", "ref_id": employee_id, "label": name or employee_id,
              "module": "hr", "props": {"department": department}}]
    edges = []
    if department:
        nodes.append({"kind": "department", "ref_id": department, "label": department, "module": "hr"})
        edges.append({"src_kind": "employee", "src_ref": employee_id, "rel": "in department",
                      "dst_kind": "department", "dst_ref": department})
    if manager_id:
        edges.append({"src_kind": "employee", "src_ref": employee_id, "rel": "reports to",
                      "dst_kind": "employee", "dst_ref": manager_id})
    ingest(org_id, nodes=nodes, edges=edges,
           event={"topic": "employee.hired", "module": "hr", "entity_kind": "employee",
                  "entity_id": employee_id, "payload": {"department": department}})
