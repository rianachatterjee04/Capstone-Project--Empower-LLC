"""The app's dependency objects are the ones the routes actually hold.

WHY THIS FILE IS NAMED TO RUN LAST
It is a check on what the rest of the suite did to the process. Any test that
calls `importlib.reload` on a module the routes were built from replaces those
function objects, and `app.dependency_overrides` -- which is keyed by function
IDENTITY -- silently stops matching. The symptom appears in some OTHER file, as
"422: header authorization Field required" on a request that was supposed to be
authenticated, with nothing in that file to explain it.

That happened. `test_dev_token_bypass_regression.py` reloaded `app.api.deps` to
exercise the production guard and never put it back, and thirteen files later a
fixture that imported `require_org` at call time got a function nobody was
using. Files importing at module scope were unaffected, because collection
happens before any test runs -- which is exactly why it went unnoticed.

This asserts the invariant directly rather than waiting for the next fixture to
trip over it.
"""
from __future__ import annotations

from app.api import deps
from app.main import app


def _route_dependency_calls():
    seen = set()
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        stack = list(dependant.dependencies)
        while stack:
            d = stack.pop()
            if d.call is not None:
                seen.add(d.call)
            stack.extend(d.dependencies)
    return seen


def test_require_org_is_the_object_the_routes_reference():
    calls = _route_dependency_calls()
    by_name = {getattr(c, "__name__", "") for c in calls}
    assert "require_org" in by_name, (
        "no route depends on require_org; this check has stopped checking")
    assert deps.require_org in calls, (
        "`app.api.deps.require_org` is not the object any route holds. Some "
        "test reloaded the module and did not restore it, so every later "
        "`app.dependency_overrides[require_org] = ...` is registering a key "
        "FastAPI will never look up.")


def test_db_session_is_the_object_the_routes_reference():
    calls = _route_dependency_calls()
    assert deps.db_session in calls, (
        "`app.api.deps.db_session` is not the object any route holds; a "
        "reloaded module has broken dependency overriding for the suite")


def test_the_settings_object_is_still_the_one_the_engine_was_built_from():
    """`app.core.config` is reloaded by the same test. The engine in
    `app.db.session` was created from the settings that existed at import, so
    a reloaded config leaves the two disagreeing about the database."""
    from app.core import config
    from app.db import session
    assert session.settings is config.settings, (
        "app.db.session and app.core.config hold different settings objects; "
        "a reload was not restored")
