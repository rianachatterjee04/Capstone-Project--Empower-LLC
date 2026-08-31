"""
Every API path the employer web app calls resolves to a route the API serves,
with the method it uses.

WHY THIS IS A TEST
Two defects of exactly this shape were live at once, both on flagship screens,
both invisible to every other test:

  The ASC 718 "Post to GL" button posted to
  /equity/grants/{id}/asc718/post-journal. That route has never existed; the
  endpoint is /equity/asc718/post-period. The page's headline capability --
  "equity expense flows into your GL" -- answered 404 and printed "Not Found"
  under the schedule.

  The interview scorecard sent POST to /interviews/{id}/scorecard/{sid}, which
  is registered PATCH only. FastAPI rejects it with 405 before the handler
  runs, so every competency rating and note a recruiter typed was discarded,
  and so was every row the AI drafter produced. The frontend function was even
  called patchRow.

Neither is findable by unit tests on either side: the API route is correct and
tested, the component renders and is tested, and nothing compares the string
one sends with the string the other answers. This test is that comparison, and
it needs no running server -- the routes come from the app object.

Run:  cd packages/hr-api && python -m pytest tests/test_frontend_routes_exist.py -q
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.main import app

_PKGS = Path(__file__).resolve().parents[3] / "packages"

# Both HR web apps. The employee-facing one was never checked and had four
# calls to /api/equity/... producing /api/api/equity/... -> 404, so an employee
# opening their own equity or total-comp page saw an error. A contract checker
# that only reads one of two clients gives false confidence about the other.
WEB_APPS = {
    "hr-web-employer": _PKGS / "hr-web-employer" / "src",
    "hr-web-employee": _PKGS / "hr-web-employee" / "src",
}

# apiFetch defaults to GET; the rest carry their verb in the name.
VERB = {"apiPost": "POST", "apiPatch": "PATCH", "apiDelete": "DELETE",
        "apiPut": "PUT", "apiObjectUrl": "GET", "apiFetch": "GET"}

CALL = re.compile(
    r"\b(apiFetch|apiPost|apiPatch|apiDelete|apiPut|apiObjectUrl)"
    r"\s*(?:<[^>]*>)?\s*\(\s*([`\"'])")


def _registered():
    out: dict[str, set[str]] = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not methods:
            continue
        out.setdefault(_norm(path), set()).update(
            m for m in methods if m not in ("HEAD", "OPTIONS"))
    return out


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), src)
    return re.sub(r"(^|[^:])//[^\n]*",
                  lambda m: m.group(1) + " " * (len(m.group()) - len(m.group(1))), src)


def _strip_interp(p: str) -> str:
    """Replace every ${...} with {}, counting braces so nesting survives.

    A path like `/recognition${v ? `?kind=${v}` : ""}` holds a nested template
    with its own braces AND quotes. A regex that stops at the first of either
    truncates the path and invents findings.
    """
    out, i = [], 0
    while i < len(p):
        if p[i:i + 2] == "${":
            depth, i = 1, i + 2
            while i < len(p) and depth:
                depth += (p[i] == "{") - (p[i] == "}")
                i += 1
            out.append("{}")
            continue
        out.append(p[i])
        i += 1
    return "".join(out)


def _norm(p: str) -> str:
    p = re.sub(r"\{[^}]*\}", "{}", _strip_interp(p))
    return p.split("?")[0].rstrip("/") or "/"


def _read_literal(src: str, i: int, quote: str) -> tuple[str, int]:
    """The literal starting at src[i], to its real closing quote."""
    out, depth = [], 0
    while i < len(src):
        c = src[i]
        if quote == "`" and src[i:i + 2] == "${":
            depth += 1
            out.append("${")
            i += 2
            continue
        if depth:
            depth += (c == "{") - (c == "}")
            out.append(c)
            i += 1
            continue
        if c == "\\":
            out.append(src[i:i + 2]); i += 2; continue
        if c == quote:
            return "".join(out), i
        out.append(c)
        i += 1
    return "".join(out), i


def _calls():
    """(file, line, verb, normalised path) for every API call in the web app."""
    for app_name, web in WEB_APPS.items():
      if not web.exists():
          continue
      for f in sorted(web.rglob("*.ts*")):
        if f.name.endswith(".d.ts") or f.name == "api.ts":
            continue
        src = _strip_comments(f.read_text())
        for m in CALL.finditer(src):
            fn, quote = m.group(1), m.group(2)
            raw, end = _read_literal(src, m.end(), quote)
            if not raw.startswith("/"):
                continue
            verb = VERB[fn]
            init = re.search(r'method:\s*["\'](\w+)["\']', src[end:end + 220])
            if fn == "apiFetch" and init:
                verb = init.group(1).upper()
            # apiPath() strips one leading "/api" because the base URL already
            # ends in one, so the wire path is exactly "/api" + the rest.
            path = raw[4:] if raw.startswith("/api/") else raw
            yield (f"{app_name}/" + str(f).split(app_name + "/")[1],
                   src[:m.start()].count("\n") + 1, verb, _norm("/api" + path))


def _resolves(n: str, verb: str, reg: dict[str, set[str]]) -> bool:
    if verb in reg.get(n, ()):
        return True
    # A trailing interpolation GLUED TO A SEGMENT is the query string:
    # `/employees${q}` normalises to /api/employees{} and is /api/employees
    # with or without ?status=active.
    #
    # It must be glued. A trailing {} that is a whole segment is a real path
    # parameter, and stripping it turned POST /interviews/{}/scorecard/{} into
    # POST /interviews/{}/scorecard -- which exists. The 405 this test was
    # written to catch reported itself as fine.
    last = n.rsplit("/", 1)[-1]
    if n.endswith("{}") and last != "{}" and verb in reg.get(n[:-2].rstrip("/"), ()):
        return True
    want = n.strip("/").split("/")

    # Same shape, wildcards on either side: `/pto/requests/${id}/${action}`
    # normalises to .../{}/{} while the routes are .../approve and .../deny.
    # The variable segment IS the action, so the call is fine.
    for path, methods in reg.items():
        if verb not in methods:
            continue
        have = path.strip("/").split("/")
        if len(have) == len(want) and all(
                w == h or "{}" in (w, h) for w, h in zip(want, have)):
            return True

    # Two ADJACENT interpolations glue a fragment on: `/investigations/${id}${p}`
    # with p = "/witness" produces one segment "{}{}", which is really two.
    # Only that pattern may span extra segments -- an earlier version allowed
    # any trailing wildcard to absorb one, and then POST /scorecard/{} matched
    # POST /scorecard/{}/draft, which is how the scorecard 405 would have gone
    # on hiding behind a neighbouring route.
    if "{}{}" not in n:
        return False
    head = want[:want.index(next(w for w in want if "{}{}" in w))]
    for path, methods in reg.items():
        if verb not in methods:
            continue
        have = path.strip("/").split("/")
        if len(have) <= len(head):
            continue
        if all(w == h or "{}" in (w, h) for w, h in zip(head, have)):
            return True
    return False


def test_the_route_table_and_the_scan_both_work():
    """CONTROL. If either side comes up empty the assertion below is vacuous."""
    reg = _registered()
    assert len(reg) > 200, f"only {len(reg)} routes found on the app object"
    calls = list(_calls())
    assert len(calls) > 200, (
        f"only {len(calls)} API calls found under "
        f"{sorted(WEB_APPS)} -- the scan has stopped reading the clients")
    # Both clients must actually be read. The employee app was invisible to
    # this checker while four of its calls 404'd.
    seen_apps = {rel.split("/")[0] for rel, *_ in calls}
    assert seen_apps == set(WEB_APPS), (
        f"scanned {sorted(seen_apps)}, expected {sorted(WEB_APPS)}")

    # Paths driven in a browser and watched return 200.
    # Cap table is not part of this build, so the two equity routes that used
    # to anchor this control are gone. Replaced with routes this build serves —
    # a control that names a removed route fails for the wrong reason and tells
    # you nothing about the checker.
    for verb, path in (("GET", "/api/comp/total"),
                       ("PATCH", "/api/interviews/{}/scorecard/{}"),
                       ("GET", "/api/employees")):
        assert _resolves(path, verb, reg), f"known-good route did not resolve: {verb} {path}"

    # ...and the two defects this test exists for must NOT resolve.
    for verb, path in (("GET", "/api/comp/total/{}/does-not-exist"),
                       ("POST", "/api/interviews/{}/scorecard/{}")):
        assert not _resolves(path, verb, reg), (
            f"{verb} {path} resolved -- the check cannot detect the defect it "
            "was written for")


def test_the_checker_catches_each_shape_of_route_defect():
    """POSITIVE CONTROLS, one per failure mode we have actually shipped.

    A contract checker is only worth its green result if it can go red. Each of
    these is a real defect shape:

      1. the scorecard verb — POST to a PATCH-only route, which FastAPI answers
         405 before the handler runs, so every rating a recruiter typed was
         discarded
      2. the doubled prefix — /api/api/equity/me, which is what the employee
         app produced for its own equity page
      3. a missing path segment — /api/interviews/{}/scorecard with the
         scorecard id dropped

    Shape 3 is the subtle one. An earlier version of _resolves let a trailing
    wildcard absorb a segment, so POST /scorecard/{} matched
    POST /scorecard/{}/draft and the 405 reported itself as fine.
    """
    reg = _registered()
    planted = [
        ("POST", "/api/interviews/{}/scorecard/{}", "wrong verb on a PATCH-only route"),
        ("GET", "/api/api/equity/me", "doubled /api prefix"),
        ("GET", "/api/api/equity/cap-table", "doubled /api prefix"),
        ("PATCH", "/api/interviews/{}/scorecard", "required path segment dropped"),
        ("POST", "/api/equity/grants/{}/asc718/post-journal", "route that never existed"),
    ]
    undetected = [f"{v} {p} ({why})" for v, p, why in planted if _resolves(p, v, reg)]
    assert undetected == [], (
        "the checker accepted these planted defects, so its clean result on the "
        "real call sites means nothing:\n  " + "\n  ".join(undetected))


def test_the_checker_does_not_flag_the_corrected_forms():
    """CONTROL, the other direction. Each planted defect above has a correct
    counterpart that must still resolve -- a checker that rejects working calls
    gets switched off."""
    reg = _registered()
    # Cap table is not in this build; these name routes it serves.
    for verb, path in (("PATCH", "/api/interviews/{}/scorecard/{}"),
                       ("GET", "/api/comp/total"),
                       ("GET", "/api/employees")):
        assert _resolves(path, verb, reg), (
            f"the corrected form {verb} {path} does not resolve")


def test_every_frontend_api_call_hits_a_real_route():
    reg = _registered()
    bad = []
    for rel, line, verb, n in _calls():
        if _resolves(n, verb, reg):
            continue
        near = sorted(p for p in reg if p.startswith(n.rsplit("/", 1)[0]))[:3]
        bad.append(f"{rel}:{line}  {verb} {n}"
                   + (f"   (nearby: {', '.join(near)})" if near else ""))
    assert bad == [], (
        "the web app calls API paths that do not exist, or exist with a "
        "different method:\n  " + "\n  ".join(bad))


# ---------------------------------------------------------------------------
# Which client is allowed to call what
# ---------------------------------------------------------------------------

_ROLE_GATE = re.compile(r"actor\.role\s+not\s+in\s*\(([^)]*)\)")
_EMPLOYEE_ROLES = {"employee", "candidate"}


def _handlers() -> dict[tuple[str, str], str]:
    """(normalised path, METHOD) -> handler source.

    Keyed by METHOD as well as path on purpose. Keyed by path alone, a POST
    handler's role gate is attributed to the GET on the same path -- which
    reported nine employee-app pages as calling HR-only endpoints. Every one was
    a false positive, and a live probe with an employee token returned 200 for
    all of them.
    """
    out: dict[tuple[str, str], str] = {}
    for r in app.routes:
        path, ep, methods = (getattr(r, "path", None), getattr(r, "endpoint", None),
                             getattr(r, "methods", None))
        if not (path and ep and methods):
            continue
        try:
            src = inspect.getsource(ep)
        except (OSError, TypeError):
            continue
        for verb in methods:
            out[(_norm(path), verb)] = src
    return out


def _roles_allowed(src: str) -> set[str] | None:
    g = _ROLE_GATE.search(src)
    if not g:
        return None
    return {x.strip().strip("\"'") for x in g.group(1).split(",") if x.strip()}


def test_the_employee_app_calls_no_recruiter_only_route():
    """An employee-facing page calling an HR-gated endpoint is a 403 in front of
    the person the page was built for."""
    handlers = _handlers()
    matched, bad = 0, []
    for rel, line, verb, path in _calls():
        if not rel.startswith("hr-web-employee"):
            continue
        src = handlers.get((path, verb))
        if src is None:
            continue
        matched += 1
        allowed = _roles_allowed(src)
        if allowed and not (allowed & _EMPLOYEE_ROLES):
            bad.append(f"{rel}:{line}  {verb} {path}  gated to {sorted(allowed)}")

    assert matched > 40, (
        f"only {matched} employee-app calls were matched to a handler; the check "
        "below would pass by not looking")
    assert bad == [], "employee-facing pages calling recruiter-only routes:\n  " + "\n  ".join(bad)


def test_the_role_check_can_see_a_gated_route():
    """CONTROL. Prove the gate parser reads a real handler, and that keying by
    method is what makes it accurate."""
    handlers = _handlers()
    gated = {k: _roles_allowed(v) for k, v in handlers.items()}
    with_gate = {k: v for k, v in gated.items() if v}
    assert with_gate, "no role gate was parsed from any handler; the check is blind"

    # At least one route must exclude employees, or "none found" is meaningless.
    excludes_employees = [k for k, v in with_gate.items() if not (v & _EMPLOYEE_ROLES)]
    assert excludes_employees, (
        "no route excludes employees, so the employee-app check cannot fail")
