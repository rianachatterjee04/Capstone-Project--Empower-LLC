#!/bin/bash
if [ -z "$1" ]; then
  echo "Usage: ./restore_db.sh <backup_file.sql>"
  exit 1
fi
echo "♻️  Restoring from $1..."
docker compose exec -T postgres psql -U postgres empower < $1
echo "✅ Restore complete!"
