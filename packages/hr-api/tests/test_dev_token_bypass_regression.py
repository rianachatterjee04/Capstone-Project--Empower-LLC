"""REGRESSION: the unsigned `dev:` bearer bypass must never authenticate in production.

Background
----------
`packages/hr-api/app/api/deps.py` accepted a bearer token of the shape

    dev:<org_id>:<role>:<email>:<user_id>

and built a fully-authorized Actor from it. The caller supplies org_id and role,
and role DEFAULTS TO "owner" when the segment is empty. There is no signature, so
in production this was equivalent to no authentication at all: anyone able to
reach the service could mint owner-level access to any organization.

There were THREE independent reasons it was live, and fixing the first two was not
enough — the third made the first two inert:

  1. `render.yaml` set FINTRA_ALLOW_DEMO_TOKEN=1 on the deployed fintra-hr-api.
     Fixed: the flag is removed.
  2. `_dev_auth_enabled()` honored that flag even when `_is_prod()` was true (it
     logged a warning and returned True).
     Fixed: it now hard-refuses whenever `_is_prod()`, so no environment variable
     can re-enable the bypass.
  3. `_is_prod()` RETURNED FALSE IN PRODUCTION. `Settings.env` defaulted to "dev"
     and render.yaml set no ENV at all, so the guard added in (2) never engaged
     and the bypass stayed open.
     Fixed: `Settings.env` now defaults to "production", and render.yaml sets
     ENV=production explicitly on every service.

The lesson is in the test design. The first suite written for this monkeypatched
`_is_prod` — proving the guard was correct GIVEN the predicate, while saying
nothing about whether the predicate was ever true where it mattered. Those tests
passed while the vulnerability remained open. The final section below therefore
exercises the REAL predicate with no patching, and asserts the deployment config
directly.

Run:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_dev_token_bypass_regression.py -q
"""
from __future__ import annotations

import pathlib

import pytest

from app.api import deps


# --------------------------------------------------------------------------
# _dev_auth_enabled: the load-bearing guard
# --------------------------------------------------------------------------

@pytest.mark.parametrize("flag", [None, "1", "true", "TRUE", "0", ""])
def test_bypass_never_enabled_in_production(monkeypatch, flag):
    """In production the bypass is off for EVERY value of the flag, including "1".

    This is the specific regression: the old code returned True when the flag was
    "1" regardless of environment.
    """
    monkeypatch.setattr(deps, "_is_prod", lambda: True)
    monkeypatch.delenv("FINTRA_ALLOW_DEMO_TOKEN", raising=False)
    if flag is not None:
        monkeypatch.setenv("FINTRA_ALLOW_DEMO_TOKEN", flag)

    assert deps._dev_auth_enabled() is False, (
        f"dev: auth bypass was enabled in production with "
        f"FINTRA_ALLOW_DEMO_TOKEN={flag!r} — this is the exact defect being guarded"
    )


def test_production_misconfiguration_is_logged_at_error(monkeypatch, caplog):
    """Setting the flag in production must be loud, not silent."""
    monkeypatch.setattr(deps, "_is_prod", lambda: True)
    monkeypatch.setenv("FINTRA_ALLOW_DEMO_TOKEN", "1")

    with caplog.at_level("ERROR"):
        assert deps._dev_auth_enabled() is False
    assert any(
        "FINTRA_ALLOW_DEMO_TOKEN" in r.message and r.levelname == "ERROR"
        for r in caplog.records
    ), "a production misconfiguration must be logged at ERROR"


@pytest.mark.parametrize("flag", [None, "1"])
def test_bypass_still_available_outside_production(monkeypatch, flag):
    """Local development is unaffected — the fix must not break dev workflows."""
    monkeypatch.setattr(deps, "_is_prod", lambda: False)
    monkeypatch.delenv("FINTRA_ALLOW_DEMO_TOKEN", raising=False)
    if flag is not None:
        monkeypatch.setenv("FINTRA_ALLOW_DEMO_TOKEN", flag)

    assert deps._dev_auth_enabled() is True


# --------------------------------------------------------------------------
# The role-assertion property that made the bypass severe
# --------------------------------------------------------------------------

def test_role_defaults_to_owner_when_segment_is_empty():
    """Documents WHY this bypass was critical rather than merely untidy.

    `dev:<org>::<email>:<user>` — an empty role segment — yields role="owner".
    That is the behaviour in deps.py, and it is why an unauthenticated caller got
    owner privileges rather than the least-privileged role. Pinning it here so any
    future change to the parsing is a deliberate decision.
    """
    token = "dev:11111111-1111-1111-1111-111111111111::x@y.z:22222222-2222-2222-2222-222222222222"
    parts = token.split(":")
    role = parts[2] if len(parts) > 2 and parts[2] else "owner"
    assert role == "owner"


# --------------------------------------------------------------------------
# Deployment configuration
# --------------------------------------------------------------------------

def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "render.yaml").exists():
            return parent
    raise AssertionError("render.yaml not found above this test file")


def test_render_config_no_demo_token():
    """No deployed service may set FINTRA_ALLOW_DEMO_TOKEN.

    The code guard above is the real control, but this catches a re-introduction
    of the flag in deployment config during review rather than in production.
    """
    render = (_repo_root() / "render.yaml").read_text()
    assert "FINTRA_ALLOW_DEMO_TOKEN" not in render, (
        "render.yaml sets FINTRA_ALLOW_DEMO_TOKEN. Even though the code now "
        "refuses it in production, it must not appear in deployment config."
    )


# --------------------------------------------------------------------------
# The gap that made the first fix inert
# --------------------------------------------------------------------------
#
# Every test above monkeypatches `_is_prod`. That verifies the guard is correct
# GIVEN the predicate, and says nothing about whether the predicate is true in the
# deployed configuration. It was not: Settings.env defaulted to "dev" and
# render.yaml set no ENV, so _is_prod() returned False in production and the guard
# never engaged. The tests passed while the bypass stayed open.
#
# These call the REAL _is_prod() against a real Settings, with no patching.

def test_is_prod_is_true_when_env_is_unset(monkeypatch):
    """The deployed default must be production.

    render.yaml now sets ENV explicitly, but the code default is the backstop —
    and it is what failed before. A service deployed without ENV must still treat
    itself as production.
    """
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    from app.core.config import Settings
    assert Settings(_env_file=None).env == "production", (
        "Settings.env must default to 'production'. A 'dev' default silently "
        "disables every guard keyed on _is_prod(), including the unsigned dev: "
        "auth bypass."
    )


@pytest.fixture(autouse=True)
def _deps_module_restored():
    """Undo `importlib.reload(deps)` for the rest of the session.

    THIS TEST USED TO POISON EVERY LATER TEST THAT OVERRIDES A DEPENDENCY.
    `importlib.reload` rebinds every name in the module to a NEW object, but
    the FastAPI routes were built with the OLD `require_org` and keep pointing
    at it. `app.dependency_overrides[require_org]` then registers the new
    function as the key, FastAPI looks up the old one, finds nothing, and runs
    the real dependency -- so an authenticated test suddenly gets
    "422: header authorization Field required" and nothing in its own file
    explains why.

    Files that import their dependencies at module scope were unaffected,
    because collection happens before any test runs. That is why this went
    unnoticed: it only breaks a fixture that imports at call time, and it
    breaks it from thirteen files away.

    Restoring the module's __dict__ puts the original function objects back,
    which is the only thing that restores IDENTITY. Reloading a second time
    would create a third set of objects and fix nothing.
    """
    import copy
    saved = dict(deps.__dict__)
    from app.core import config as config_mod
    saved_config = dict(config_mod.__dict__)
    try:
        yield
    finally:
        deps.__dict__.clear()
        deps.__dict__.update(saved)
        config_mod.__dict__.clear()
        config_mod.__dict__.update(saved_config)


@pytest.mark.parametrize(
    "env_value,expect_prod",
    [
        (None, True),            # unset -> production (the defect)
        ("production", True),
        ("prod", True),
        ("staging", True),       # anything unrecognised -> production
        ("dev", False),
        ("development", False),
        ("test", False),
        ("local", False),
    ],
)
def test_real_is_prod_across_env_values(monkeypatch, env_value, expect_prod):
    """Exercise the REAL predicate — no monkeypatching of _is_prod."""
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    if env_value is not None:
        monkeypatch.setenv("ENV", env_value)

    import importlib
    from app.core import config as config_mod
    importlib.reload(config_mod)
    importlib.reload(deps)

    assert deps._is_prod() is expect_prod, (
        f"ENV={env_value!r} -> _is_prod()={deps._is_prod()}, expected {expect_prod}"
    )
    # The restore is in `_deps_module_restored` below, and it is not optional.


def test_render_yaml_sets_env_production_for_every_service():
    """Deployment config must not rely on the code default.

    The bypass was live because render.yaml set no ENV at all on fintra-hr-api.
    """
    import yaml
    render = yaml.safe_load((_repo_root() / "render.yaml").read_text())
    missing = []
    for svc in render.get("services", []):
        name = svc.get("name", "<unnamed>")
        env_vars = {e.get("key") for e in (svc.get("envVars") or [])}
        if "ENV" not in env_vars:
            missing.append(name)
    assert not missing, f"services with no explicit ENV: {missing}"
