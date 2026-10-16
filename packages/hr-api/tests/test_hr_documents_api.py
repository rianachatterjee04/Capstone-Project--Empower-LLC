"""HTTP tests for uploading and managing HR documents.

No live model. Each test uses its own organisation id, so nothing carries over.

Run:  python -m pytest tests/test_hr_documents_api.py -v
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Actor, db_session, require_org
from app.main import app
from app.services import rag_service
from tests._hr_doc_fixtures import make_docx, make_pdf

POLICY = "Employees may work remotely up to three days a week with manager approval."
QUESTION = "How many days can I work remotely"
BASE = "/api/ai-helpdesk"


class _FakeDB:
    def add(self, *_a, **_k):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.clear()


def _as(role: str, org: str) -> TestClient:
    actor = Actor(user_id=str(uuid.uuid4()), org_id=org, role=role,
                  claims={"email": f"{role}@test.io"})
    app.dependency_overrides[require_org] = lambda: actor
    app.dependency_overrides[db_session] = lambda: _FakeDB()
    return TestClient(app)


def _upload(c, name="remote.txt", data=POLICY.encode(), ctype="text/plain", **form):
    return c.post(f"{BASE}/documents/upload", files={"file": (name, data, ctype)}, data=form)


def _retrieved_ids(org: str) -> list[str]:
    return [d.id for d in rag_service.retrieve(org, QUESTION, top_k=5)]


# --- upload ------------------------------------------------------------------

def test_upload_stores_the_file_and_the_helpdesk_can_find_it():
    org = str(uuid.uuid4())
    c = _as("hr", org)
    r = _upload(c, title="Remote work", category="policy")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Remote work" and body["status"] == "active"
    assert body["filename"] == "remote.txt" and body["kind"] == "txt"
    assert body["size_bytes"] == len(POLICY) and body["chars"] == len(POLICY)
    assert body["id"] in _retrieved_ids(org)


@pytest.mark.parametrize("name,data,ctype", [
    ("remote.docx", make_docx([POLICY]),
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("remote.pdf", make_pdf([POLICY]), "application/pdf"),
    ("remote.md", f"# Remote\n\n{POLICY}".encode(), "text/markdown"),
])
def test_each_format_uploads_and_is_searchable(name, data, ctype):
    org = str(uuid.uuid4())
    c = _as("owner", org)
    r = _upload(c, name=name, data=data, ctype=ctype)
    assert r.status_code == 200, r.text
    assert r.json()["id"] in _retrieved_ids(org)


def test_title_defaults_to_the_file_name():
    c = _as("admin", str(uuid.uuid4()))
    r = _upload(c, name="Remote_Work-policy.txt")
    assert r.json()["title"] == "Remote Work policy"


@pytest.mark.parametrize("role", ["employee", "manager"])
def test_only_hr_roles_can_upload(role):
    c = _as(role, str(uuid.uuid4()))
    assert _upload(c).status_code == 403


def test_a_refused_file_returns_the_reason_and_stores_nothing():
    org = str(uuid.uuid4())
    c = _as("hr", org)
    before = len(rag_service.list_documents(org))
    r = _upload(c, name="policy.pdf", data=b"not a pdf", ctype="application/pdf")
    assert r.status_code == 415
    assert "PDF" in r.json()["detail"]
    assert len(rag_service.list_documents(org)) == before


def test_file_over_the_limit_is_refused_with_413():
    c = _as("hr", str(uuid.uuid4()))
    r = _upload(c, data=b"a" * (5 * 1024 * 1024 + 10))
    assert r.status_code == 413


def test_the_same_file_twice_is_refused_with_409():
    c = _as("hr", str(uuid.uuid4()))
    assert _upload(c, title="First").status_code == 200
    r = _upload(c, title="Second")
    assert r.status_code == 409 and "First" in r.json()["detail"]


def test_the_same_file_can_be_uploaded_by_another_organisation():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert _upload(_as("hr", a)).status_code == 200
    assert _upload(_as("hr", b)).status_code == 200


def test_a_bad_category_is_refused_with_400():
    c = _as("hr", str(uuid.uuid4()))
    assert _upload(c, category="../../etc").status_code == 400


# --- management --------------------------------------------------------------

def _uploaded(org: str, **kw) -> tuple[TestClient, str]:
    c = _as("hr", org)
    r = _upload(c, **kw)
    assert r.status_code == 200, r.text
    return c, r.json()["id"]


def test_list_shows_uploaded_details_to_admins():
    org = str(uuid.uuid4())
    c, doc_id = _uploaded(org, title="Remote work")
    items = {i["id"]: i for i in c.get(f"{BASE}/documents").json()["items"]}
    assert items[doc_id]["meta"]["filename"] == "remote.txt"
    assert items[doc_id]["status"] == "active"


def test_list_hides_archived_documents_and_uploader_details_from_employees():
    org = str(uuid.uuid4())
    admin, doc_id = _uploaded(org)
    assert admin.post(f"{BASE}/documents/{doc_id}/archive").status_code == 200
    employee = _as("employee", org)
    items = employee.get(f"{BASE}/documents").json()["items"]
    assert doc_id not in [i["id"] for i in items]
    assert all("meta" not in i for i in items)


def test_archive_removes_it_from_answers_and_restore_brings_it_back():
    org = str(uuid.uuid4())
    c, doc_id = _uploaded(org)
    assert doc_id in _retrieved_ids(org)

    r = c.post(f"{BASE}/documents/{doc_id}/archive")
    assert r.status_code == 200 and r.json()["status"] == "archived"
    assert doc_id not in _retrieved_ids(org)

    r = c.post(f"{BASE}/documents/{doc_id}/restore")
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert doc_id in _retrieved_ids(org)


def test_restore_is_refused_when_the_same_file_is_active_again():
    org = str(uuid.uuid4())
    c, first = _uploaded(org, title="First")
    c.post(f"{BASE}/documents/{first}/archive")
    assert _upload(c, title="Second").status_code == 200
    r = c.post(f"{BASE}/documents/{first}/restore")
    assert r.status_code == 409


def test_edit_changes_title_and_category():
    org = str(uuid.uuid4())
    c, doc_id = _uploaded(org, title="Old")
    r = c.patch(f"{BASE}/documents/{doc_id}", json={"title": "New title", "category": "time_off"})
    assert r.status_code == 200
    assert r.json()["title"] == "New title" and r.json()["category"] == "time_off"


def test_edit_with_nothing_to_change_is_400():
    c, doc_id = _uploaded(str(uuid.uuid4()))
    assert c.patch(f"{BASE}/documents/{doc_id}", json={}).status_code == 400


def test_delete_removes_the_document_for_good():
    org = str(uuid.uuid4())
    c, doc_id = _uploaded(org)
    r = c.delete(f"{BASE}/documents/{doc_id}")
    assert r.status_code == 200 and r.json() == {"deleted": True, "id": doc_id}
    assert doc_id not in [d["id"] for d in rag_service.list_documents(org)]
    assert doc_id not in _retrieved_ids(org)
    assert c.delete(f"{BASE}/documents/{doc_id}").status_code == 404


def test_a_deleted_documents_id_is_never_given_to_a_new_one():
    """The old id scheme used len(docs)+1, so a delete could cause a duplicate."""
    org = str(uuid.uuid4())
    c, first = _uploaded(org, name="a.txt", data=b"first policy text about remote work days")
    r = _upload(c, name="b.txt", data=b"second policy text about remote work days")
    second = r.json()["id"]
    c.delete(f"{BASE}/documents/{first}")
    third = _upload(c, name="c.txt", data=b"third policy text about remote work days").json()["id"]
    ids = [d["id"] for d in rag_service.list_documents(org)]
    assert len(ids) == len(set(ids))
    assert third != second


def test_built_in_documents_can_be_archived_but_not_deleted_or_edited():
    org = str(uuid.uuid4())
    c = _as("hr", org)
    builtin = c.get(f"{BASE}/documents").json()["items"][0]["id"]
    assert c.delete(f"{BASE}/documents/{builtin}").status_code == 409
    assert c.patch(f"{BASE}/documents/{builtin}", json={"title": "x"}).status_code == 409
    assert c.post(f"{BASE}/documents/{builtin}/archive").status_code == 200


@pytest.mark.parametrize("method,path", [
    ("patch", "/documents/{id}"),
    ("post", "/documents/{id}/archive"),
    ("post", "/documents/{id}/restore"),
    ("delete", "/documents/{id}"),
])
def test_employees_cannot_manage_documents(method, path):
    org = str(uuid.uuid4())
    _, doc_id = _uploaded(org)
    employee = _as("employee", org)
    kwargs = {"json": {"title": "x"}} if method == "patch" else {}
    r = getattr(employee, method)(BASE + path.format(id=doc_id), **kwargs)
    assert r.status_code == 403


@pytest.mark.parametrize("method,path", [
    ("patch", "/documents/{id}"),
    ("post", "/documents/{id}/archive"),
    ("post", "/documents/{id}/restore"),
    ("delete", "/documents/{id}"),
])
def test_another_organisation_cannot_see_or_change_a_document(method, path):
    owner_org, other_org = str(uuid.uuid4()), str(uuid.uuid4())
    _, doc_id = _uploaded(owner_org)
    intruder = _as("owner", other_org)
    kwargs = {"json": {"title": "hijacked"}} if method == "patch" else {}
    r = getattr(intruder, method)(BASE + path.format(id=doc_id), **kwargs)
    assert r.status_code == 404
    # the owner's document is untouched
    assert doc_id in _retrieved_ids(owner_org)
    assert doc_id not in [d["id"] for d in rag_service.list_documents(other_org)]


def test_unknown_document_is_404():
    c = _as("hr", str(uuid.uuid4()))
    assert c.post(f"{BASE}/documents/doc-nope/archive").status_code == 404
