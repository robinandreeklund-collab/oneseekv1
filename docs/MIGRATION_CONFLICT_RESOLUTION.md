# Alembic Migration Conflict Resolution

## Issue

When running `alembic upgrade head`, the following error occurred:

```
/mnt/c/Users/robin/Documents/GitHub/oneseekv1/surfsense_backend/venv/lib/python3.12/site-packages/alembic/script/revision.py:213: UserWarning: Revision 100 is present more than once
  util.warn(
ERROR [alembic.util.messaging] Multiple head revisions are present for given argument 'head'; please specify a specific target revision
```

## Root Cause

The tool lifecycle migration was created with revision ID "100", which conflicted with an existing migration:
- `100_add_tool_retrieval_tuning.py` (existing)
- `100_add_tool_lifecycle_status.py` (newly created) ❌

Both migrations had `revision = "100"` and `down_revision = "99"`, creating multiple heads in the migration chain.

## Resolution Steps

### Attempt 1: Change to Revision 101
Initially tried to change the tool lifecycle migration to revision 101, but discovered:
- `101_add_tool_evaluation_runs_global.py` already existed with revision 101 ❌

### Attempt 2: Find Next Available Revision
Scanned all migration files to find the highest numeric revision:
- Highest existing: 103 (`103_add_global_intent_definitions.py`)
- Next available: 104 ✅

### Final Solution
Changed the tool lifecycle migration to revision 104:

**File renamed:**
```
100_add_tool_lifecycle_status.py → 104_add_tool_lifecycle_status.py
```

**Updated metadata:**
```python
# Before
revision: str = "100"
down_revision: str | None = "99"

# After
revision: str = "104"
down_revision: str | None = "103"
```

## Verification

After the fix:
- ✅ No duplicate revisions exist
- ✅ Total migrations: 97
- ✅ Migration chain is correct: ... → 103 → 104
- ✅ `alembic upgrade head` should now work

## Migration Chain

The corrected migration chain (last 11 migrations):

```
 94 ← 94_add_agent_prompt_overrides.py
 95 ← 95_add_agent_prompt_override_history.py
 96 ← 96_add_global_agent_prompt_overrides.py
 97 ← 97_add_chat_trace_tables.py
 98 ← 98_add_agent_combo_cache.py
 99 ← 99_add_tool_metadata_overrides.py
100 ← 100_add_tool_retrieval_tuning.py
101 ← 101_add_tool_evaluation_runs_global.py
102 ← 102_add_tool_evaluation_stage_runs_global.py
103 ← 103_add_global_intent_definitions.py
104 ← 104_add_tool_lifecycle_status.py (FIXED)
```

## Best Practices for Future Migrations

To avoid this issue in the future:

1. **Check existing revisions** before creating a new migration:
   ```bash
   ls -1 alembic/versions/ | grep -E '^[0-9]+_' | sort -n | tail -5
   ```

2. **Use Alembic's automatic revision generation** (if configured):
   ```bash
   alembic revision --autogenerate -m "Description"
   ```

3. **Always verify** no duplicates exist:
   ```python
   # Check for duplicate revisions
   import os, re
   versions_dir = 'alembic/versions'
   revisions = {}
   for f in os.listdir(versions_dir):
       if f.endswith('.py'):
           with open(os.path.join(versions_dir, f)) as file:
               match = re.search(r'revision: str = "(\w+)"', file.read())
               if match:
                   rev = match.group(1)
                   if rev in revisions:
                       print(f"❌ Duplicate: {rev}")
                   revisions[rev] = f
   ```

4. **Commit migrations immediately** after creating them to avoid conflicts with other developers

## Testing

To test that the migration works:

```bash
cd surfsense_backend

# Check current revision
alembic current

# Check available heads (should be one)
alembic heads

# Run the migration
alembic upgrade head

# Verify the table was created
psql -d surfsense -c "\d global_tool_lifecycle_status"
```

## Related Files

- Migration file: `surfsense_backend/alembic/versions/104_add_tool_lifecycle_status.py`
- Model: `surfsense_backend/app/db.py` (GlobalToolLifecycleStatus)
- Service: `surfsense_backend/app/services/tool_lifecycle_service.py`
- Routes: `surfsense_backend/app/routes/admin_tool_lifecycle_routes.py`

## Commits

- Commit 7b74454: Initial fix attempt (100 → 101)
- Commit f9a58c4: Final fix (101 → 104)
