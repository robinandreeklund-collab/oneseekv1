# Tool Lifecycle Management System - Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     TOOL LIFECYCLE FLOW                                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  New Tool   │
│   Added     │
└──────┬──────┘
       │
       │ Default Status
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         REVIEW STATUS                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ • Not available in production (respect_lifecycle=True)                  │
│ • Available for eval testing (respect_lifecycle=False)                  │
│ • Waiting for validation                                                │
└──────┬──────────────────────────────────────────────────────────────────┘
       │
       │ Run Evaluation
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    EVALUATION & METRICS SYNC                            │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. Eval runs with respect_lifecycle=False (all tools)                  │
│ 2. Results grouped by tool_id                                           │
│ 3. _sync_eval_to_lifecycle() called automatically                       │
│ 4. Metrics updated: success_rate, total_tests, last_eval_at            │
└──────┬──────────────────────────────────────────────────────────────────┘
       │
       │ success_rate ≥ required_success_rate (80%)
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   PROMOTION ELIGIBLE                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ • Toggle switch enabled in UI                                           │
│ • Admin can promote to live                                             │
│ • Audit trail: user, timestamp, notes                                   │
└──────┬──────────────────────────────────────────────────────────────────┘
       │
       │ Admin promotes via UI or API
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         LIVE STATUS                                      │
├─────────────────────────────────────────────────────────────────────────┤
│ • Available in production (model can use it)                            │
│ • Included in build_tools_async() when respect_lifecycle=True          │
│ • Emergency rollback available                                          │
└──────┬──────────────────────────────────────────────────────────────────┘
       │
       │ If issues occur
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    EMERGENCY ROLLBACK                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ • Immediate return to REVIEW status                                     │
│ • Requires notes explaining reason                                      │
│ • Tool removed from production instantly                                │
│ • Can be re-evaluated and promoted again later                          │
└─────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                    COMPONENT ARCHITECTURE                                │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────┐
│         Frontend UI          │
│   (tool-lifecycle-page.tsx)  │
├──────────────────────────────┤
│ • Summary cards              │
│ • Search & filter            │
│ • Status table               │
│ • Toggle switches            │
│ • Rollback dialog            │
└───────────┬──────────────────┘
            │
            │ HTTP REST API
            ▼
┌──────────────────────────────┐
│    Backend API Routes        │
│ (admin_tool_lifecycle_routes)│
├──────────────────────────────┤
│ • GET /admin/tool-lifecycle  │
│ • PUT /admin/tool-lifecycle  │
│ • POST .../rollback          │
└───────────┬──────────────────┘
            │
            │ Service Layer
            ▼
┌──────────────────────────────┐
│   Tool Lifecycle Service     │
│ (tool_lifecycle_service.py)  │
├──────────────────────────────┤
│ • get_live_tool_ids()        │
│ • set_tool_status()          │
│ • update_eval_metrics()      │
│ • get_all_tool_lifecycle...  │
└───────────┬──────────────────┘
            │
            │ Database ORM
            ▼
┌──────────────────────────────┐
│        Database Layer        │
│          (db.py)             │
├──────────────────────────────┤
│ • GlobalToolLifecycleStatus  │
│ • ToolLifecycleStatus enum   │
└──────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                     INTEGRATION POINTS                                   │
└─────────────────────────────────────────────────────────────────────────┘

1. TOOL REGISTRY (registry.py)
   ┌────────────────────────────────────────┐
   │ build_tools_async()                    │
   │                                        │
   │ if respect_lifecycle:                  │
   │   live_tools = get_live_tool_ids()    │
   │   filter enabled_tools to live_tools  │
   │                                        │
   │ return filtered tools                  │
   └────────────────────────────────────────┘

2. EVAL INTEGRATION (admin_tool_settings_routes.py)
   ┌────────────────────────────────────────┐
   │ After eval completes:                  │
   │                                        │
   │ 1. _record_eval_stage_summaries()     │
   │ 2. _sync_eval_to_lifecycle()          │
   │    └─ Groups results by tool_id       │
   │    └─ Calculates success_rate         │
   │    └─ Updates lifecycle metrics       │
   └────────────────────────────────────────┘

3. SUPERVISOR AGENT (supervisor_agent.py)
   ┌────────────────────────────────────────┐
   │ Production:                            │
   │   tools = await build_tools_async(     │
   │     respect_lifecycle=True             │
   │   )                                    │
   │                                        │
   │ Eval Context:                          │
   │   tools = await build_tools_async(     │
   │     respect_lifecycle=False            │
   │   )                                    │
   └────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                       DATA FLOW                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Eval   │────▶│  Metrics │────▶│ Lifecycle│────▶│Tool      │
│  Run    │     │  Sync    │     │  Status  │     │Registry  │
└─────────┘     └──────────┘     └──────────┘     └──────────┘
                                       │
                                       │
                                       ▼
                                 ┌──────────┐
                                 │Production│
                                 │  Model   │
                                 └──────────┘
                             (Only live tools)


┌─────────────────────────────────────────────────────────────────────────┐
│                    ERROR HANDLING                                        │
└─────────────────────────────────────────────────────────────────────────┘

If lifecycle check fails:
┌────────────────────────────────────────┐
│ 1. Log warning                         │
│ 2. Fall back to original behavior      │
│ 3. Load all tools                      │
│ 4. System remains operational          │
└────────────────────────────────────────┘

This ensures system availability even if lifecycle management has issues.
```
