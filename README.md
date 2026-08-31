# Foundry People — HR platform (ASU evaluation build)

A standalone carve-out of the Foundry People HR product: one API and two web
frontends, with nothing else from the wider Fintra monorepo.

| Package | What it is | Runs on |
|---|---|---|
| `packages/hr-api` | FastAPI + SQLAlchemy (asyncpg) HR backend | `:8000` by default |
| `packages/hr-web-employer` | Next.js employer/HR-admin app, `basePath: /people` | `:3001` |
| `packages/hr-web-employee` | Next.js employee self-service portal | `:3002` |
| `packages/shared-py` | Small shared Python helpers used by `hr-api` | — |

## What is deliberately not here

**The cap table / equity module is not part of this build.** The ASC-718
engine, the equity router, its two migrations, its eleven tables, and both
frontends' equity pages have been removed rather than disabled. This is a
carve-out, not a feature flag: there is no configuration that turns it back on.

Where equity was part of a larger answer — total compensation is the only such
place — the API reports it as **unavailable, with a reason**, and the UI shows
that reason. It does not report zero. "We cannot compute this here" and "this
employee has no equity" are different statements, and only the first is true.

Twenty other packages from the source monorepo (accounting, payroll, growth,
and so on) are also absent. Two total-comp components therefore report
themselves unavailable out of the box — sales commission and payroll gross YTD.
That is expected, and the reason is shown in the response.

## Quickstart

Requires Python 3.11+, Node 20+, and a local PostgreSQL you can create
databases in.

```bash
createdb hr_demo
cd packages/hr-api
DATABASE_URL="postgresql+asyncpg:///hr_demo" ./scripts/bootstrap_hr.sh
```

That is idempotent and does everything: creates the schema, applies every
migration in order, and seeds a demo org (Northwind Robotics, 10 employees with
compensation and performance records). It should finish with **108 tables** and
**10 employees**.

Then start the API. `ENV=development` matters — the API treats an unset
environment as production, which disables the dev-auth bypass:

```bash
cd packages/hr-api
ENV=development DATABASE_URL="postgresql+asyncpg:///hr_demo" \
  PYTHONPATH=../shared-py python3 -m uvicorn app.main:app --port 8000
```

And either frontend:

```bash
cd packages/hr-web-employer && npm install && npm run dev
```

The employer app is at **http://localhost:3001/people** (note the `/people`
base path — the bare root is a 404 by design). The employee portal runs with
`npm run dev` in `packages/hr-web-employee` and is at
**http://localhost:3002/app**.

Both frontends read `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000/api`). The realtime websocket is derived from it, so
pointing the app at a different port moves both.

### Signing in

The employer app gates on a client-side demo credential —
`demo@fintra-hr.test` / `FintraHrDemo2026!`, overridable with
`NEXT_PUBLIC_DEMO_EMAIL` and `NEXT_PUBLIC_DEMO_PASSWORD`. This is a demo gate,
not an authentication system: it validates in the browser and is not a security
boundary. Real authentication is Supabase JWT against the API.

The employee portal has no login in this build; it identifies itself as a
seeded employee (`liam.eng@northwind.test`, override with
`NEXT_PUBLIC_DEV_EMPLOYEE_EMAIL`) so self-service pages have a real person to
show.

## Porting the schema to your own Supabase

`packages/hr-api` talks to Postgres through SQLAlchemy and `DATABASE_URL`, not
through the Supabase client, so a Supabase Postgres is just another
`DATABASE_URL`.

```bash
cd packages/hr-api
DATABASE_URL="postgresql+asyncpg://postgres:<password>@db.<ref>.supabase.co:5432/postgres" \
  python3 scripts/bootstrap_supabase.py
```

The script applies every migration and then **verifies the result against
`scripts/expected_tables.txt`**, exiting non-zero and naming what is missing if
the schema came out incomplete. Run it twice; it is idempotent.

`expected_tables.txt` is the contract, and `tests/test_supabase_bootstrap_is_complete.py`
guards it in both directions — a migration that adds a table without updating
the list fails, and a listed table that no migration creates fails too.

## Tests

```bash
./tools/gate.sh all
```

On a fresh clone this is **1,274 passing, 0 failing** — the Python suites and
the storage-safety guard. The frontend steps report themselves as SKIPPED until you
`npm install` in each web package; with those installed it is **1,344 passing**,
adding the employer app's `node --test` suite and a TypeScript compile of both
frontends.

A skipped step says so on its own line rather than passing quietly, which is
the point: this gate once reported 1,337 passing over a frontend that would not
compile.

That last step is newer than the rest, and worth knowing why it exists: the
gate reported 1,337 passing while the employee portal returned HTTP 500 on its
compensation page and the employer app could not compile its audit page. No
Python test compiles TypeScript, and the JS suite reads source as text rather
than type-checking it, so a broken frontend sat behind a green gate. Both
compile steps are verified to fail on a planted type error rather than assumed
to work.

Database-backed tests need a reachable local Postgres; without one they skip,
and the gate says so rather than quietly passing.

## Known gaps

- Commission and payroll gross YTD are always unavailable here — the packages
  that serve them are not part of this build.
- The employer demo login is client-side only, as described above.
- `docs/manuals/` carries the HR user guides. Anything they mention that is not
  in the table at the top of this file — accounting, payroll, compliance — is a
  seam to a service that does not ship in this build.
