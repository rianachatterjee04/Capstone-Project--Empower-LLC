

run setup.sh script in the backend and npm run build in the backend
#!/bin/bash


# 1. CLEAN SLATE
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
cd ../..

# 3. Start Core Services
echo "🐳 Building and Starting Database & Backend..."
docker compose up -d --build postgres backend

# 4. Wait for Database Health
echo "⏳ Waiting for Database to be fully ready..."
until [ "$(docker inspect -f '{{.State.Health.Status}}' empower-postgres)" == "healthy" ]; do
    printf "."
    sleep 1
done
echo " Ready!"

# 5. Initialize Database Tables
echo "🏗️ Initializing Database Tables inside the container..."
docker compose exec backend python init_db_fixed.py

# 6. Seed Default Organization
echo "🌱 Seeding Default Organization (1111-1111)..."
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
    print('✅ Seeded Organization')
asyncio.run(seed())
"

# 7. Start AI Orchestrator
echo "🤖 Starting AI Orchestrator..."
docker compose up -d orchestrator

# 8. Setup Frontend
echo "💻 Checking Frontend Dependencies..."
cd apps/web-employer
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm packages (this may take a minute)..."
    npm install
fi
cd ../..
echo "✅ SETUP COMPLETE!"
echo "-------------------------------------------------------"
echo "Check AI Logs:   docker compose logs -f orchestrator"
echo "Start Frontend:  cd apps/web-employer && npm run dev"
echo "-------------------------------------------------------"
docker compose ps

echo "\nYou now have a fully functional environment:"
echo "Database:    empower-postgres (Port 5432)"
echo "API:         empower-backend  (Port 8000)"
echo "AI worker:   empower-orchestrator (Internal)"
echo "UI:          Next.js (Port 3000)"
