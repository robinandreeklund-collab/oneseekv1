# OneSeek LangSmith Default Prompt Template

This file documents the canonical prompt template exposed to LangSmith/LangGraph Studio.

Source of truth:

- `app/agents/new_chat/prompt_registry.py`
- `ONESEEK_LANGSMITH_PROMPT_TEMPLATE_KEYS`

Only prompts that are used in the current OneSeek LangGraph flow are included.
Legacy prompt keys from older routing/sub-route flows are intentionally removed.

## Flow order

### 1) Platform ingress

1. `system.default.instructions`
2. `citation.instructions`
3. `router.top_level`
4. `agent.smalltalk.system`

### 2) Supervisor orchestration (LangGraph)

5. `agent.supervisor.system`
6. `compare.supervisor.instructions`
7. `supervisor.intent_resolver.system`
8. `supervisor.agent_resolver.system`
9. `supervisor.planner.system`
10. `supervisor.tool_resolver.system`
11. `supervisor.critic_gate.system`
12. `supervisor.synthesizer.system`
13. `supervisor.critic.system`
14. `supervisor.loop_guard.message`
15. `supervisor.tool_limit_guard.message`
16. `supervisor.trafik.enforcement.message`
17. `supervisor.code.sandbox.enforcement.message`
18. `supervisor.code.read_file.enforcement.message`
19. `supervisor.scoped_tool_prompt.template`
20. `supervisor.tool_default_prompt.template`
21. `supervisor.subagent.context.template`
22. `supervisor.hitl.planner.message`
23. `supervisor.hitl.execution.message`
24. `supervisor.hitl.synthesis.message`

### 3) Worker prompts

25. `agent.worker.knowledge`
26. `agent.knowledge.system`
27. `agent.worker.action`
28. `agent.action.system`
29. `agent.media.system`
30. `agent.browser.system`
31. `agent.code.system`
32. `agent.kartor.system`
33. `agent.statistics.system`
34. `agent.synthesis.system`
35. `agent.bolag.system`
36. `agent.trafik.system`
37. `agent.riksdagen.system`
38. `agent.marketplace.system`

### 4) Compare execution

39. `compare.analysis.system`
40. `compare.external.system`
