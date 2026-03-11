import asyncio
from uuid import UUID
from app.db.session import engine
from sqlalchemy import text

async def seed():
    async with engine.begin() as conn:
        print("🌱 Seeding default Organization...")
        await conn.execute(
            text("INSERT INTO orgs (id, name) VALUES (:id, :name) ON CONFLICT DO NOTHING"),
            {"id": "11111111-1111-1111-1111-111111111111", "name": "Default Dev Org"}
        )
        print("✅ Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed())
