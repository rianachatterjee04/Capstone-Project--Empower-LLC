# Foundry People (AI-native HR OS) — DB + RLS edition

Locked stack:
- Frontend: React + Next.js (App Router)
- Backend: FastAPI (async) + SQLAlchemy
- Data/Auth: Supabase Postgres + Auth + Storage

This package upgrades the previous MVP by adding:
✅ Full Postgres schema
✅ Supabase Row Level Security (RLS) policies
✅ Backend endpoints migrated from in-memory stubs to DB

## 1) Supabase setup
1. Create a Supabase project
2. Run migrations in `infra/supabase/migrations` (SQL editor or `supabase db push`)
3. Ensure your users have `app_metadata.org_id` and `app_metadata.role`

### Required JWT claims
- `app_metadata.org_id` (uuid as string)
- `app_metadata.role` in: owner/admin/hr/manager/employee

## 2) Backend setup
```bash
cd apps/backend
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 3) Web portals
Employer:
```bash
cd apps/web-employer
cp .env.example .env.local
npm install
npm run dev
```

Employee:
```bash
cd apps/web-employee
cp .env.example .env.local
npm install
npm run dev
```

## Notes
- The backend enforces tenant isolation in queries. Supabase RLS also enforces isolation when using direct PostgREST access.
- Sensitive onboarding values should be encrypted at-rest in production (KMS). This repo stores minimal PII by default (SSN last4 only).

## Enterprise modules added
- AI Memory (per-tenant vector memory)
- Policy compiler (English → DSL)
- Escalation engine (SLA timers + overdue bumps)
- Documents (storage pointers + verification stub)
- Realtime WS scaffold
- Mobile app scaffold (Expo)


### Added (full production foundations)
- Market benchmarking provider pattern + capture endpoint
- Bonus pool + payout calculator
- Benefits optimization MVP
- True manager-subtree RLS (recursive)
- Supabase Storage signed upload (best-effort) + HR verification queue
- View audit logging + /api/audit/views
- ATS syndication scaffolding
- Celery background job runner (Redis)

## v4 Additions: AI Memory + Policy DSL + Executive Mobile + CFO Dashboard
### AI Memory (Production)
- Set `OPENAI_API_KEY`
- Set `EMBEDDINGS_PROVIDER=openai` (or `mock`)
- Uses `ai_memory_chunks` (pgvector) + `ai_decisions` for decision lineage

### Policy DSL → Execution UI
- Employer portal: `/app/policies-exec`
- Backend: `/api/policies2/*` endpoints
- Temporal escalation workflow stub: `apps/backend/app/temporal/workflows/escalation.py`

### Executive Mobile App (Expo)
- `cd apps/mobile-exec && npm i && npm run start`
- Registers Expo push token via `/api/push/register`
- Approvals feed: `/api/approvals/pending`

### CFO Scenario Modeling
- Employer portal: `/app/cfo`
- Backend: `/api/cfo/scenario` + `/api/cfo/org-summary`

### Temporal
- `docker compose -f infra/temporal/docker-compose.yml up -d`
- Run worker: `python -m app.temporal.worker`

## v5: Fully operational ATS sync (Greenhouse + Lever)
### Configure secrets
- Set `INTEGRATIONS_ENC_KEY` (Fernet key) for token encryption (generate with Python: `from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`)
- Greenhouse: set `GREENHOUSE_API_KEY` or connect via UI by pasting key
- Lever: set `LEVER_CLIENT_ID`, `LEVER_CLIENT_SECRET`, `LEVER_REDIRECT_URI`
- Webhook secrets: set `GREENHOUSE_WEBHOOK_SECRET` / `LEVER_WEBHOOK_SECRET` (or use the secrets created per-org in the Integrations UI)

### Run Temporal
- `docker compose -f infra/temporal/docker-compose.yml up -d`
- `cd apps/backend && uvicorn app.main:app --reload`
- In another terminal: `cd apps/backend && python -m app.temporal.worker`

### ATS sync outputs
- Jobs: `public.ats_job_postings`
- Candidates: `public.ats_candidates`

## v6: Event replay + stage mapping + AI screening loop (Greenhouse/Lever)
See /app/ats-mapping and POST /api/integrations/replay/{provider}

## v7 Authority Layer
Adds AI authority governance, policy consequences, human decision ledger,
authority delegation, time-aware org constraints, and board exports.
# Capstone-Project--Empower-LLC
