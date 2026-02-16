# Backend (FastAPI + Supabase Postgres)

New enterprise modules:
- AI Memory (pgvector): `/api/ai/memory/*`
- Policies (English → DSL): `/api/policies`
- Escalations (SLA timers + run loop): `/api/escalations/*`
- Documents (storage pointers + verification stub): `/api/documents/*`
- Realtime WS stub: `/api/ws`

To run:
```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
