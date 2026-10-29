"""Employee skills and role skill requirements.

The database calls are replaced with a small in memory stand in, so these tests
check the rules and the permissions, not Postgres. The SQL itself is short and is
covered by running the migration and using the page.

Run:  python -m pytest tests/test_skills_management.py -v
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Actor, db_session, require_org
from app.main import app
from app.services import skills_management_service as svc

BASE = "/api/skills-management"


# --- the rules, with no database ---------------------------------------------

def test_names_are_lower_cased_and_tidied():
    assert svc.clean_name("  Python  ") == "python"
    assert svc.clean_name("CI/CD   Pipelines") == "ci/cd pipelines"


@pytest.mark.parametrize("bad", ["", "   ", None, 5, "x" * 81])
def test_bad_names_are_refused(bad):
    with pytest.raises(svc.SkillsError):
        svc.clean_name(bad)


@pytest.mark.parametrize("good", [1, 2, 3, 4])
def test_levels_one_to_four_are_accepted(good):
    assert svc.check_level(good) == good


@pytest.mark.parametrize("bad", [0, 5, -1, 2.5, "3", None, True])
def test_other_levels_are_refused(bad):
    with pytest.raises(svc.SkillsError):
        svc.check_level(bad)


def test_requirements_are_cleaned_and_a_repeated_skill_keeps_the_last_level():
    out = svc.clean_requirements([
        {"skill": "SQL", "required_level": 2},
        {"skill": " sql ", "required_level": 3},
        {"skill": "python"},
    ])
    assert out == [
        {"skill": "python", "required_level": svc.DEFAULT_LEVEL},
        {"skill": "sql", "required_level": 3},
    ]


def test_requirements_must_be_a_list_of_objects():
    with pytest.raises(svc.SkillsError):
        svc.clean_requirements("python")
    with pytest.raises(svc.SkillsError):
        svc.clean_requirements(["python"])


def test_compare_to_role_sorts_each_requirement_into_met_below_or_missing():
    skills = [{"skill": "python", "level": 3}, {"skill": "sql", "level": 1}]
    needs = [
        {"skill": "python", "required_level": 3},
        {"skill": "sql", "required_level": 2},
        {"skill": "aws", "required_level": 2},
    ]
    out = svc.compare_to_role(skills, needs)
    assert [r["skill"] for r in out["met"]] == ["python"]
    assert [r["skill"] for r in out["below"]] == ["sql"]
    assert [r["skill"] for r in out["missing"]] == ["aws"]
    assert out["coverage_percent"] == 33


def test_compare_to_an_empty_role_is_zero_not_a_crash():
    assert svc.compare_to_role([], [])["coverage_percent"] == 0


def test_a_built_in_role_has_a_starting_list():
    items = svc.default_requirements("Software Engineer")
    assert {"skill": "python", "required_level": svc.DEFAULT_LEVEL} in items


def test_an_unknown_role_has_no_starting_list():
    assert svc.default_requirements("Astronaut") == []


# --- the endpoints, with a stand in for the database -------------------------

ORG = str(uuid.uuid4())
ME = str(uuid.uuid4())      # the employee record that belongs to the signed in user
OTHER = str(uuid.uuid4())   # a different employee in the same organisation
STRANGER = str(uuid.uuid4())  # an employee in a different organisation


class _Fake:
    """In memory version of the database functions the router calls."""

    def __init__(self):
        self.skills: dict[tuple[str, str], dict] = {}
        self.roles: dict[str, list[dict]] = {}

    async def employee_exists(self, _db, org_id, employee_id):
        return employee_id in (ME, OTHER) and org_id == ORG

    async def employee_id_for_user(self, _db, _org_id, _user_id):
        return ME

    async def list_employee_skills(self, _db, _org, employee_id):
        return [v for (e, _), v in sorted(self.skills.items()) if e == employee_id]

    async def save_employee_skill(self, _db, _org, employee_id, skill, level, source):
        name, lv = svc.clean_name(skill), svc.check_level(level)
        row = {"skill": name, "level": lv, "level_name": svc.LEVEL_NAMES[lv],
               "source": source, "updated_at": None}
        self.skills[(employee_id, name)] = row
        return row

    async def remove_employee_skill(self, _db, _org, employee_id, skill):
        return self.skills.pop((employee_id, svc.clean_name(skill)), None) is not None

    async def list_roles(self, _db, _org):
        return [{"role": r, "skill_count": len(v), "is_default": False} for r, v in self.roles.items()]

    async def get_role_requirements(self, _db, _org, role):
        name = svc.clean_name(role, "role")
        if name in self.roles:
            return {"role": name, "items": self.roles[name], "is_default": False}
        return {"role": name, "items": svc.default_requirements(name), "is_default": True}

    async def set_role_requirements(self, _db, _org, role, items):
        name = svc.clean_name(role, "role")
        self.roles[name] = svc.clean_requirements(items)
        return await self.get_role_requirements(None, None, name)


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake(monkeypatch):
    f = _Fake()
    for name in ("employee_exists", "employee_id_for_user", "list_employee_skills",
                 "save_employee_skill", "remove_employee_skill", "list_roles",
                 "get_role_requirements", "set_role_requirements"):
        monkeypatch.setattr(svc, name, getattr(f, name))
    return f


def _as(role: str) -> TestClient:
    actor = Actor(user_id=str(uuid.uuid4()), org_id=ORG, role=role, claims={"email": f"{role}@test.io"})
    app.dependency_overrides[require_org] = lambda: actor
    app.dependency_overrides[db_session] = lambda: object()
    return TestClient(app)


def test_hr_can_add_a_skill_for_anyone_and_it_is_marked_as_set_by_hr(fake):
    c = _as("hr")
    r = c.post(f"{BASE}/employees/{OTHER}/skills", json={"skill": "Python", "level": 3})
    assert r.status_code == 200, r.text
    assert r.json()["skill"] == "python" and r.json()["source"] == "hr"
    items = c.get(f"{BASE}/employees/{OTHER}/skills").json()["items"]
    assert [i["skill"] for i in items] == ["python"]


def test_an_employee_can_add_their_own_skill_marked_as_self_reported(fake):
    r = _as("employee").post(f"{BASE}/employees/{ME}/skills", json={"skill": "sql", "level": 2})
    assert r.status_code == 200 and r.json()["source"] == "self"


def test_an_employee_cannot_read_or_change_a_colleague(fake):
    c = _as("employee")
    assert c.get(f"{BASE}/employees/{OTHER}/skills").status_code == 403
    assert c.post(f"{BASE}/employees/{OTHER}/skills", json={"skill": "sql", "level": 2}).status_code == 403
    assert c.delete(f"{BASE}/employees/{OTHER}/skills", params={"skill": "sql"}).status_code == 403


def test_a_manager_can_read_but_not_change(fake):
    c = _as("manager")
    assert c.get(f"{BASE}/employees/{OTHER}/skills").status_code == 200
    assert c.post(f"{BASE}/employees/{OTHER}/skills", json={"skill": "sql", "level": 2}).status_code == 403


def test_an_employee_from_another_organisation_is_not_found_even_for_hr(fake):
    assert _as("hr").get(f"{BASE}/employees/{STRANGER}/skills").status_code == 404


def test_saving_the_same_skill_again_updates_the_level(fake):
    c = _as("hr")
    c.post(f"{BASE}/employees/{OTHER}/skills", json={"skill": "sql", "level": 1})
    c.post(f"{BASE}/employees/{OTHER}/skills", json={"skill": "SQL", "level": 4})
    items = c.get(f"{BASE}/employees/{OTHER}/skills").json()["items"]
    assert len(items) == 1 and items[0]["level"] == 4


@pytest.mark.parametrize("body", [
    {"skill": "", "level": 2},
    {"skill": "sql", "level": 9},
    {"skill": "sql"},
    {"level": 2},
])
def test_bad_skill_requests_are_a_400(fake, body):
    assert _as("hr").post(f"{BASE}/employees/{OTHER}/skills", json=body).status_code == 400


def test_removing_a_skill_works_once_then_it_is_a_404(fake):
    c = _as("hr")
    c.post(f"{BASE}/employees/{OTHER}/skills", json={"skill": "ci/cd", "level": 2})
    assert c.delete(f"{BASE}/employees/{OTHER}/skills", params={"skill": "ci/cd"}).status_code == 200
    assert c.delete(f"{BASE}/employees/{OTHER}/skills", params={"skill": "ci/cd"}).status_code == 404


def test_anyone_can_read_a_built_in_role_and_it_is_marked_as_default(fake):
    r = _as("employee").get(f"{BASE}/roles/requirements", params={"role": "software engineer"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_default"] is True and any(i["skill"] == "python" for i in body["items"])


def test_only_hr_can_change_role_requirements(fake):
    body = {"role": "driver", "items": [{"skill": "cdl", "required_level": 3}]}
    assert _as("employee").put(f"{BASE}/roles/requirements", json=body).status_code == 403
    assert _as("manager").put(f"{BASE}/roles/requirements", json=body).status_code == 403
    r = _as("hr").put(f"{BASE}/roles/requirements", json=body)
    assert r.status_code == 200 and r.json()["is_default"] is False
    assert r.json()["items"] == [{"skill": "cdl", "required_level": 3}]


def test_a_bad_requirement_is_a_400_and_changes_nothing(fake):
    c = _as("hr")
    r = c.put(f"{BASE}/roles/requirements", json={"role": "driver", "items": [{"skill": "cdl", "required_level": 7}]})
    assert r.status_code == 400
    assert "driver" not in fake.roles
