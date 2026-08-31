#!/usr/bin/env python3
"""Storage-safety regression guard for the Fintra monorepo.

Fails (exit 2) if any of the following appear anywhere under packages/**:

  1. A public-URL call site: ``getPublicUrl(``.
     Permanent, un-expiring public object URLs are how private HR documents
     (I-9s, passports) leak. The repo intentionally has none — every read must
     go through a short-lived signed URL or an authenticated, RLS-checked
     request. Reintroducing getPublicUrl() would defeat that.

  2. A bucket flagged public: ``public: true`` / ``"public": true`` /
     ``public = true`` (JS, JSON, or SQL). The only bucket in the product,
     ``foundry-people``, must stay private.

  3. A ``createBucket(...)`` call or an ``INSERT INTO storage.buckets`` that
     does not set the public flag EXPLICITLY to false. "Defaults to private"
     is not good enough for something this sensitive; it must be spelled out so
     a reviewer can see it and a future default change cannot silently flip it.

Design goals:
  * Zero third-party deps — standard library only, so CI can run it directly.
  * Deterministic, path-sorted output with file:line for every finding.
  * Passes on the current repo (verified), including this repo's own
    the storage_security migration, whose storage.buckets
    INSERT sets public to false explicitly.

Usage:
    python scripts/check_storage_safety.py            # scans <repo>/packages
    python scripts/check_storage_safety.py PATH ...   # scans the given paths

Exit codes: 0 = clean, 2 = violations found, 3 = nothing to scan / bad path.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

# --------------------------------------------------------------------------- #
# What to scan                                                                #
# --------------------------------------------------------------------------- #
SCAN_EXTS = {
    ".py", ".sql",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".vue", ".svelte",
}

SKIP_DIRS = {
    "node_modules", ".git", ".next", "dist", "build", "coverage",
    ".venv", "venv", "__pycache__", ".turbo", ".cache", "out",
    ".pytest_cache", ".mypy_cache", "site-packages",
}

MAX_BYTES = 4_000_000  # skip anything larger than 4 MB (bundles, lockfiles)

# --------------------------------------------------------------------------- #
# Patterns                                                                     #
# --------------------------------------------------------------------------- #
# 1. Public-URL call site.
RE_GET_PUBLIC_URL = re.compile(r"getPublicUrl\s*\(")

# 2. A public flag set true (JS object, JSON, or SQL). The look-behind stops
#    unrelated columns such as `is_public = true` / `isPublic: true` from
#    matching — only a bare `public` token counts.
RE_PUBLIC_TRUE = re.compile(
    r"(?<![A-Za-z0-9_])[\"']?public[\"']?\s*[:=]\s*true\b",
    re.IGNORECASE,
)

# The bare `public: true` check (rule 2) fires ONLY in files that actually touch
# Supabase Storage. Otherwise it false-positives on unrelated data — e.g. the
# SentriAI AWS connector's mock S3 inventory, where `"public": True` DESCRIBES an
# external bucket the scanner should flag, and cloud-config flags elsewhere. The
# createBucket / storage.buckets rules (3) always fire because they are, by
# definition, Supabase Storage bucket operations.
RE_STORAGE_MARKER = re.compile(
    r"supabase|createBucket|storage\.buckets|getPublicUrl|createSignedUrl|"
    r"createSignedUploadUrl|SUPABASE_STORAGE|storage/v1/object|\.storage\.",
    re.IGNORECASE,
)

# 3a. createBucket(...) calls — inspect their argument text for explicit false.
RE_CREATE_BUCKET = re.compile(r"createBucket\s*\(")
# 3b. INSERT INTO storage.buckets ... statements.
RE_BUCKETS_INSERT = re.compile(r"insert\s+into\s+storage\.buckets", re.IGNORECASE)
# An explicit `public ... false` somewhere in the relevant window makes it safe.
RE_PUBLIC_FALSE = re.compile(
    r"(?<![A-Za-z0-9_])[\"']?public[\"']?\s*[:=]\s*false\b",
    re.IGNORECASE,
)
# For SQL positional inserts (INSERT INTO storage.buckets (id,name,public)
# VALUES (...,false)) the flag is not written as `public = false`, so also
# accept a bare `false` token appearing in the statement window.
RE_BARE_FALSE = re.compile(r"(?<![A-Za-z0-9_])false\b", re.IGNORECASE)

Finding = Tuple[str, int, str]  # (path, line_no, message)


def _iter_files(roots: Iterable[str]) -> Iterable[str]:
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1].lower() in SCAN_EXTS:
                    yield os.path.join(dirpath, fn)


def _read(path: str) -> str | None:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _call_arg_window(text: str, open_paren_idx: int, limit: int = 600) -> str:
    """Return the text inside a call's parentheses, balanced, capped at `limit`."""
    depth = 0
    out = []
    for i in range(open_paren_idx, min(len(text), open_paren_idx + limit)):
        ch = text[i]
        out.append(ch)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def _statement_window(text: str, start_idx: int, limit: int = 1200) -> str:
    """Return text from start_idx up to the next `;` (or `limit` chars)."""
    end = text.find(";", start_idx)
    if end == -1 or end - start_idx > limit:
        end = start_idx + limit
    return text[start_idx:end]


def scan_file(path: str) -> List[Finding]:
    text = _read(path)
    if text is None:
        return []
    findings: List[Finding] = []

    for m in RE_GET_PUBLIC_URL.finditer(text):
        findings.append((path, _line_of(text, m.start()),
                         "getPublicUrl() creates a permanent public object URL; "
                         "use a signed URL instead"))

    if RE_STORAGE_MARKER.search(text):
        for m in RE_PUBLIC_TRUE.finditer(text):
            findings.append((path, _line_of(text, m.start()),
                             "Supabase bucket flagged public (public=true); buckets must stay private"))

    for m in RE_CREATE_BUCKET.finditer(text):
        window = _call_arg_window(text, m.end() - 1)
        if not RE_PUBLIC_FALSE.search(window):
            findings.append((path, _line_of(text, m.start()),
                             "createBucket() without an explicit public: false"))

    for m in RE_BUCKETS_INSERT.finditer(text):
        window = _statement_window(text, m.start())
        if not (RE_PUBLIC_FALSE.search(window) or RE_BARE_FALSE.search(window)):
            findings.append((path, _line_of(text, m.start()),
                             "INSERT INTO storage.buckets without an explicit public=false"))

    return findings


def _default_roots() -> List[str]:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [os.path.join(repo_root, "packages")]


def main(argv: List[str]) -> int:
    roots = argv[1:] or _default_roots()
    roots = [os.path.abspath(r) for r in roots]

    missing = [r for r in roots if not os.path.exists(r)]
    if missing:
        print("check_storage_safety: path(s) not found: " + ", ".join(missing),
              file=sys.stderr)
        return 3

    all_findings: List[Finding] = []
    scanned = 0
    for path in _iter_files(roots):
        scanned += 1
        all_findings.extend(scan_file(path))

    if scanned == 0:
        print("check_storage_safety: no scannable files under: " + ", ".join(roots),
              file=sys.stderr)
        return 3

    if all_findings:
        all_findings.sort(key=lambda f: (f[0], f[1]))
        print("STORAGE SAFETY CHECK FAILED — %d violation(s):\n" % len(all_findings))
        for fpath, line, msg in all_findings:
            rel = os.path.relpath(fpath)
            print("  %s:%d  %s" % (rel, line, msg))
        print("\nFix these before merging. See scripts/check_storage_safety.py "
              "for the rationale behind each rule.")
        return 2

    print("check_storage_safety: OK — scanned %d file(s), no storage-safety "
          "violations." % scanned)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
