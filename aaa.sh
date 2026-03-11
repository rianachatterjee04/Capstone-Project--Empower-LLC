#!/bin/bash

# 1. CLEAN SLATE: Kill existing containers
echo "🧹 Cleaning up existing Docker containers..."
docker compose down --remove-orphans

# 2. Setup Backend Environment
echo "🚀 Syncing Environment Secrets..."
cd apps/backend

if [ ! -f .env ]; then
    cp .env.example .env
fi

# Ensure secrets match (Mac-compatible sed)
sed -i '' 's/INTERNAL_AI_SHARED_SECRET=.*/INTERNAL_AI_SHARED_SECRET=dev-internal-secret/' .env
sed -i '' 's/BACKEND_URL=.*/BACKEND_URL=http:\/\/backend:8000/' .env

# We skip local venv/pip here because Docker handles dependencies internally
cd ../..

# 3. Start Core Services
echo "🐳 Building and Starting Database & Backend..."
docker compose up -d --build postgres backend

echo "⏳ Waiting 15s for Database to be ready..."
sleep 15

# 4. Initialize Database (RUNNING INSIDE DOCKER)
echo "🏗️ Initializing Database Tables inside the container..."
# Using 'docker compose exec' ensures it uses the container's Python and connectivity
docker compose exec backend python -c "
import asyncio
try:
    from app.db.session import engine
    from app.db.models import Base
    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print('\n✅ --- DATABASE SCHEMA SYNCED ---')
    asyncio.run(init())
except Exception as e:
    print(f'\n❌ DB INIT ERROR: {e}')
"

# 5. Start AI Orchestrator
echo "🤖 Starting AI Orchestrator..."
docker compose up -d --force-recreate orchestrator


# ... inside setup.sh after tables are created ...

echo "🌱 Seeding Database with Default Org..."
docker compose exec backend python -c "
import asyncio
from app.db.session import engine
from sqlalchemy import text
async def seed():
    async with engine.begin() as conn:
        await conn.execute(
            text(\"INSERT INTO orgs (id, name) VALUES (:id, :name) ON CONFLICT DO NOTHING\"),
            {\"id\": \"11111111-1111-1111-1111-111111111111\", \"name\": \"Default Dev Org\"}
        )
    print('✅ Seeded Organization 1111-1111...')
asyncio.run(seed())
"

# 6. Setup Frontend
echo "💻 Setting up Frontend..."
cd apps/web-employer
if [ ! -d "node_modules" ]; then
    npm install
fi

echo "✅ SETUP COMPLETE!"
echo "-------------------------------------------------------"
echo "Check AI Logs: docker compose logs -f orchestrator"
echo "Start Frontend: cd apps/web-employer && npm run dev"
echo "-------------------------------------------------------"
docker compose ps

echo "\nYou now have a fully functional environment:"
echo "Database: empower-postgres (Port 5432)"
echo "API: empower-backend (Port 8000)"
echo "AI worker: empower-orchestrator (Internal)"
echo "UI: Next.js (Port 3000)"
