#!/bin/bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="backup_${TIMESTAMP}.sql"
echo "📦 Creating backup: $BACKUP_FILE"
docker compose exec -T postgres pg_dump -U postgres empower > $BACKUP_FILE
echo "✅ Backup saved to $BACKUP_FILE"
