# Tool Lifecycle Management System - Usage Guide

## Overview

The Tool Lifecycle Management System provides a gating mechanism where tools are validated via evaluation before becoming available in production. This ensures only tested and reliable tools are accessible to the AI model.

## Lifecycle Statuses

- **review**: New tools start here. Only available for eval testing, not in production.
- **live**: Validated tools that have met success criteria. Available for the model in production.

## How It Works

### 1. New Tools Start in Review

When a new tool is added to the registry, it automatically starts in "review" status. The tool will NOT be available to the AI model in production (when `respect_lifecycle=True`, which is the default).

### 2. Run Evaluations

Use the Tool Settings admin page to run evaluations:
- Eval tests can access ALL tools (including review status) because eval uses `respect_lifecycle=False`
- After eval completes, metrics are automatically synced to the lifecycle table
- Each tool gets its success rate and test count updated

### 3. Check Lifecycle Status

Navigate to **Admin → Tool Lifecycle** to see:
- Summary cards: Live count, Review count, Total count
- Table with all tools showing:
  - Tool ID
  - Current status (live/review badge)
  - Success rate from latest eval
  - Required threshold (default 80%)
  - Last eval timestamp
  - Last status change info

### 4. Promote to Live

To promote a tool from review to live:
1. Ensure the tool has been evaluated and meets the threshold (≥80% success rate by default)
2. Click the toggle switch in the Actions column
3. The switch is disabled if the tool doesn't meet the threshold
4. Hover over the button to see why it's disabled

### 5. Emergency Rollback

If a live tool is causing issues:
1. Click the red shield icon (🛡️) next to live tools
2. Enter a reason for the rollback (required)
3. Click "Bekräfta Rollback"
4. The tool immediately returns to review status and is removed from production

## API Endpoints

### List All Tools
```
GET /admin/tool-lifecycle
```

Returns all tools with their lifecycle status and metrics.

### Update Tool Status
```
PUT /admin/tool-lifecycle/{tool_id}
Content-Type: application/json

{
  "status": "live",  // or "review"
  "notes": "Optional notes about the change"
}
```

Validates that the tool meets requirements before promotion.

### Emergency Rollback
```
POST /admin/tool-lifecycle/{tool_id}/rollback
Content-Type: application/json

{
  "notes": "Reason for emergency rollback"
}
```

Immediately sets tool back to review status.

## For Developers

### Tool Registry Integration

When calling `build_tools_async()`:

```python
# Production mode (default) - only live tools
tools = await build_tools_async(
    dependencies=deps,
    respect_lifecycle=True  # Default
)

# Eval mode - all tools including review
tools = await build_tools_async(
    dependencies=deps,
    respect_lifecycle=False  # For testing
)
```

### Service Functions

```python
from app.services.tool_lifecycle_service import (
    get_live_tool_ids,
    set_tool_status,
    update_eval_metrics,
    get_all_tool_lifecycle_statuses,
)

# Get only live tools
live_tools = await get_live_tool_ids(session)

# Update status
await set_tool_status(
    session,
    tool_id="my_tool",
    status=ToolLifecycleStatus.LIVE,
    user_id=user.id,
    notes="Promoted after successful eval"
)

# Update eval metrics (called automatically)
await update_eval_metrics(
    session,
    tool_id="my_tool",
    success_rate=0.85,
    total_tests=100
)
```

### Database Migration

Run migrations to create the lifecycle table:

```bash
cd surfsense_backend
alembic upgrade head
```

## Configuration

### Default Threshold

The required success rate defaults to 80%. This can be modified in the database:

```sql
UPDATE global_tool_lifecycle_status
SET required_success_rate = 0.90
WHERE tool_id = 'my_tool';
```

### Bootstrap Existing Tools

To initialize lifecycle statuses for existing tools:

```python
from app.services.tool_lifecycle_service import initialize_tool_lifecycle_statuses
from app.agents.new_chat.tools.registry import get_all_tool_names

tool_names = get_all_tool_names()
created_count = await initialize_tool_lifecycle_statuses(
    session,
    tool_ids=tool_names,
    default_status=ToolLifecycleStatus.LIVE  # or REVIEW
)
```

## Error Handling

The system is designed with fallback behavior:

- If lifecycle check fails, it falls back to loading all tools
- Logs warnings instead of failing hard
- This ensures the system remains available even if lifecycle management has issues

## Audit Trail

All status changes are tracked with:
- Who made the change (user_id)
- When it was changed (timestamp)
- Notes explaining the change
- Previous metrics preserved

## Best Practices

1. **Always run evals before promoting**: Ensure tools meet quality standards
2. **Use meaningful notes**: Document why status changes are made
3. **Monitor metrics**: Check success rates regularly in the admin UI
4. **Quick rollback**: Use emergency rollback immediately if issues arise
5. **Review eval results**: Check that tools are actually working as expected before promotion

## Troubleshooting

### Tool not showing up in production
- Check if tool has "live" status in Admin → Tool Lifecycle
- Verify tool is registered in the registry
- Ensure tool meets success rate threshold if trying to promote

### Eval can't find tool
- Eval always uses `respect_lifecycle=False`, so all tools should be available
- Check if tool is properly registered in the tool registry
- Verify database connection and migrations are up to date

### Can't promote tool to live
- Check success rate meets threshold (default 80%)
- Run eval if no metrics exist
- Verify eval completed successfully and synced metrics
