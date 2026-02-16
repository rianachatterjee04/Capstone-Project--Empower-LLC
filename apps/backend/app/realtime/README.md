# Real-time / Event System (scaffold)

Options:
1) Supabase Realtime (Postgres WAL) for table change subscriptions
2) WebSocket gateway in FastAPI for events (behind auth)
3) Event bus + workflow engine (Temporal recommended) for enterprise

This repo includes a minimal WS endpoint stub at `/api/ws` (not used by UI yet).
