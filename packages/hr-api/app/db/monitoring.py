"""
Query monitoring and logging for the database.
"""
import asyncio
import logging
from app.db.session import engine
from sqlalchemy import text
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def enable_monitoring():
    async with engine.begin() as conn:
        print("📊 Enabling query monitoring and logging...")

        # Enable pg_stat_statements for query tracking
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
            print("  ✅ pg_stat_statements extension enabled")
        except Exception as e:
            print(f"  ⚠️  pg_stat_statements: {str(e)[:60]}")

        # Create slow query log table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id SERIAL PRIMARY KEY,
                query_text TEXT,
                duration_ms FLOAT,
                table_name TEXT,
                operation TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        print("  ✅ query_logs table created")

        # Create error log table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id SERIAL PRIMARY KEY,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                endpoint TEXT,
                user_id TEXT,
                org_id TEXT,
                stack_trace TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        print("  ✅ error_logs table created")

        # Create index on logs for fast querying
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_query_logs_created_at ON query_logs(created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON error_logs(created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_error_logs_error_type ON error_logs(error_type)"))
        print("  ✅ indexes on log tables created")

        # Create view for slow queries (over 1000ms)
        await conn.execute(text("""
            CREATE OR REPLACE VIEW slow_queries AS
            SELECT * FROM query_logs
            WHERE duration_ms > 1000
            ORDER BY duration_ms DESC
        """))
        print("  ✅ slow_queries view created")

        print("✅ Monitoring enabled!")

async def log_error(error_type: str, message: str, endpoint: str = None, user_id: str = None, org_id: str = None):
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO error_logs (error_type, error_message, endpoint, user_id, org_id)
            VALUES (:error_type, :message, :endpoint, :user_id, :org_id)
        """), {
            "error_type": error_type,
            "message": message,
            "endpoint": endpoint,
            "user_id": user_id,
            "org_id": org_id
        })
        logger.error(f"[{error_type}] {message} | endpoint={endpoint} | user={user_id}")

if __name__ == "__main__":
    asyncio.run(enable_monitoring())
