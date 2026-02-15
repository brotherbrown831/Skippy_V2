# Claude Code Instructions for Skippy V2

## ⚠️ CRITICAL: Database Data Preservation

**NEVER delete or destroy existing database volumes or data without explicit user permission.**

### Database Migration Protocol

When making schema changes or deploying new features that require database updates:

1. **ALWAYS check for existing data** before making any database changes
   ```bash
   docker exec skippy_v2-postgres-1 psql -U skippy -d skippy -c "SELECT COUNT(*) FROM semantic_memories; SELECT COUNT(*) FROM people;"
   ```

2. **If data exists, ALWAYS create a backup:**
   ```bash
   docker exec skippy_v2-postgres-1 pg_dump -U skippy skippy > /tmp/skippy_backup_$(date +%Y%m%d_%H%M%S).sql
   ```

3. **For schema changes, use migrations instead of destructive rebuilds:**
   - Create migration SQL files in `db/migrations/` folder
   - Apply migrations with `docker exec skippy_v2-postgres-1 psql -U skippy -d skippy < db/migrations/001_add_new_table.sql`
   - Do NOT delete and recreate volumes

4. **Only delete volumes if explicitly authorized:**
   - User must explicitly say "delete the database" or "start fresh"
   - Even then, confirm with: "This will permanently delete X memories and Y people. Proceed?"
   - Always offer to create a backup first

### Safe Deployment Process

When deploying code changes:

1. ✅ Deploy new code (Docker rebuild)
2. ✅ Run migrations (if needed)
3. ✅ Test with existing data
4. ❌ DO NOT: Delete postgres_data volume
5. ❌ DO NOT: Drop and recreate tables
6. ❌ DO NOT: Run `docker volume rm` without explicit permission

### Example Safe Restart

```bash
# Safe: Rebuilds app, preserves database
docker compose down
docker rmi skippy_v2-skippy:latest
docker compose up -d

# Dangerous (don't do this):
docker volume rm skippy_v2_postgres_data  # ← This destroys all data!
```

## Project-Specific Notes

- **Memories**: Currently ~50+ in database (growing collection)
- **People**: Currently ~250+ with fuzzy deduplication active
- **HA Entities**: 823 synced (re-synced automatically, less critical)
- **Preferences**: User settings, preferences, reminders (should be preserved)

## When to Ask Permission

Ask for explicit confirmation before:
- Deleting any Docker volumes
- Dropping any database tables
- Running destructive operations (reset --hard, rm -rf, etc.)
- Rebuilding from scratch
- Any operation that could cause data loss

## Questions to Always Ask

If uncertain about data preservation:

1. "Do you want me to back up the current database first?"
2. "I found X memories and Y people. Should I preserve them?"
3. "I need to make schema changes. Should I create a migration or rebuild?"

---

**Last Updated:** Feb 15, 2026
**Status:** Critical Instruction - Follow Always
