# Backend (FastAPI + Supabase Postgres)

New enterprise modules:
- AI Memory (pgvector): `/api/ai/memory/*`
- Policies (English → DSL): `/api/policies`
- Escalations (SLA timers + run loop): `/api/escalations/*`
- Documents (storage pointers + verification stub): `/api/documents/*`
- Realtime WS stub: `/api/ws`

run this docker-compose.yml using this command in the top folder where this file is 
docker-compose up -d
python init_db_fixed.py
docker ps
docker compose up -d orchestrator
docker exec -it empower-backend python -m alembic upgrade head
docker logs empower-orchestrator
python -c "from app.db.session import engine; from app.db.models import Base; import app.db.models; Base.metadata.create_all(bind=engine)"
python init_db_fixed.py


To run:
```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip -m install -r requirements.txt
source .venv/bin/activate
pip install asyncpg
uvicorn app.main:app --reload --port 8000

npm run build
npm run dev


# 1. Create the environment file
cp .env.example .env

# 2. Setup the Python environment to run the DB initialization script
python -m venv .venv
source .venv/bin/activate
pip install -r apps/backend/requirements.txt
pip install asyncpg  # Just in case it's missing from requirements

# 5. Start the AI Orchestrator (Now that the DB/Backend are ready)
docker-compose up -d orchestrator

# 6. Check if everything is running
docker ps

# 7. Verify the AI is not crashing
docker logs empower-orchestrator


# 8. Start the frontend on the Mac
cd apps/frontend
npm install
npm run dev

