-- view_events.id is NOT NULL and had no server default. The SQLAlchemy model
-- declares default=uuid.uuid4, which is a PYTHON-side default -- it applies to
-- ORM inserts and is never invoked by a raw INSERT statement.
--
-- The view-audit middleware inserts raw SQL, so every audit write failed on the
-- id before it could fail on anything else. Combined with the wrong column
-- names (route/user_agent for path/meta), the table has never held a row: the
-- record of who viewed what does not exist for any request ever served.
--
-- The middleware now supplies its own id, so this default is belt and braces --
-- but any other raw insert would have hit the same wall, and a NOT NULL column
-- with no default on a table written by raw SQL is a trap worth removing.
-- pgcrypto is already installed (gen_random_uuid is available).

ALTER TABLE public.view_events
    ALTER COLUMN id SET DEFAULT gen_random_uuid();
