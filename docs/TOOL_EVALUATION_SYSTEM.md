# Tool Selection Evaluation System

## Overview

The Tool Selection Evaluation System provides a comprehensive testing framework for evaluating how well the tool retrieval pipeline selects appropriate tools for user queries — **without making any real API calls** to external services (SCB, Trafikverket, Bolagsverket, etc.).

The system uses the **exact same scoring/embedding/reranking pipeline** as production to ensure results are representative.

## Key Features

### Four-Layer Evaluation Pipeline

1. **Route Classification** - Tests `dispatch_route()` regex patterns
   - Routes: `knowledge`, `action`, `statistics`, `smalltalk`, `compare`

2. **Sub-route Classification** - Tests knowledge_router/action_router patterns
   - Knowledge sub-routes: `docs`, `internal`, `external`
   - Action sub-routes: `web`, `media`, `travel`, `data`

3. **Agent Selection** - Tests `_smart_retrieve_agents()` from supervisor_agent.py
   - Evaluates which agents are selected for a query
   - Measures Jaccard similarity for partial matches
   - **Note**: Currently disabled as agent definitions are not exported at module level

4. **Tool Retrieval** - Tests `smart_retrieve_tools()` from bigtool_store.py
   - Full scoring pipeline: keyword matching + semantic embeddings + reranking
   - Namespace-aware scoring with primary/fallback namespaces
   - Cross-encoder reranking of top candidates

### Match Types

- **Exact Match** - Selected tools exactly match expected tools
- **Acceptable Match** - Selected tools are within acceptable set
- **Partial Match** - Some overlap between selected and expected
- **No Match** - No overlap (failure case)

### Comprehensive Metrics

- **Accuracy rates** per layer (route, sub-route, agent, tool)
- **Composite scoring** with configurable weights across all layers
- **Latency tracking** per query
- **Confusion matrix** for route classification
- **Failure pattern detection** by tag clustering
- **Auto-generated recommendations** based on results

## Architecture

### Backend Components

#### 1. `app/services/tool_eval_service.py`

Core evaluation engine with:

- **Data models**: `TestCase`, `CategorySuite`, `EvalConfig`, `EvalSuite`, `SingleResult`, `CategoryResult`, `EvalReport`
- **Evaluation functions**:
  - `_eval_route()` - Route classification using regex only (no LLM)
  - `_eval_sub_route()` - Sub-route classification using regex
  - `evaluate_single()` - Evaluate one test case through all 4 layers
  - `run_evaluation()` - Run full suite with aggregation
- **Stub tool registry builder** - Creates tools with correct metadata but no real implementations
- **Scoring detail extraction** - Shows keyword matches, semantic scores, etc.
- **Report generation** - Comprehensive metrics, confusion matrix, recommendations

#### 2. `app/routes/admin_tool_eval_routes.py`

Three FastAPI endpoints (all require admin auth):

- **`POST /admin/tool-eval/single`** - Test single query
  ```json
  {
    "query": "Finns det några trafikstörningar på E4?",
    "expected_tools": ["trafikverket_trafikinfo_storningar"],
    "limit": 2
  }
  ```

- **`POST /admin/tool-eval/run`** - Upload and run test suite (multipart form)
  ```bash
  curl -F "file=@eval_suite.json" http://localhost:8000/api/v1/admin/tool-eval/run
  ```

- **`POST /admin/tool-eval/invalidate-cache`** - Clear cached tool index
  ```json
  {"success": true, "message": "Tool index cache cleared successfully"}
  ```

#### 3. `eval_suites/full_pipeline_eval_v1.json`

Comprehensive test suite with 80 test cases across 4 categories:

- **Trafikverket** (20 cases) - All 22 Trafikverket tools
- **Bolagsverket** (20 cases) - All 18 Bolagsverket tools  
- **General Tools** (20 cases) - SMHI, Trafiklab, Libris, Jobad, podcast, scrape, etc.
- **Adversarial** (20 cases) - Edge cases, ambiguous queries, misspellings, injections

### Frontend Components

#### 1. `app/admin/tools/eval/page.tsx`

Page route at `/admin/tools/eval` that renders the evaluation dashboard.

#### 2. `components/admin/tool-eval-page.tsx`

Main React component with two tabs:

**Single Query Tester**
- Input field for query
- Optional expected tools field
- "Testa" button
- Results display with:
  - Match type badge
  - Selected tools list
  - Scoring table (base score, semantic score, matched keywords)
  - Latency

**Suite Upload**
- File input for JSON test suite
- "Kör Utvärdering" button
- Comprehensive results dashboard:
  - Summary cards (exact rate, acceptable rate, composite score, latency)
  - Category results table
  - By-difficulty breakdown
  - Route confusion matrix
  - Failure patterns by tag
  - Failed tests accordion with diagnostics
  - Auto-recommendations

#### 3. `contracts/types/admin-tool-eval.types.ts`

TypeScript types and Zod schemas for all request/response models.

#### 4. `lib/apis/admin-tool-eval-api.service.ts`

API service class with methods for all three endpoints.

## Usage Guide

### Running a Single Query Test

1. Navigate to `/admin/tools/eval` in the admin dashboard
2. Enter a query in the "Query" field (e.g., "Finns det några trafikstörningar på E4?")
3. Optionally enter expected tools (comma-separated)
4. Click "Testa"
5. Review the results:
   - Match type
   - Selected tools
   - Detailed scoring breakdown
   - Matched keywords

### Running a Full Evaluation Suite

1. Navigate to `/admin/tools/eval` in the admin dashboard
2. Switch to the "Suite Upload" tab
3. Click "Välj JSON-fil" and select your test suite JSON file
4. Click "Kör Utvärdering"
5. Wait for evaluation to complete (progress shown with spinner)
6. Review comprehensive results:
   - Overall metrics in summary cards
   - Per-category breakdown
   - Confusion matrices
   - Failure patterns
   - Detailed diagnostics for failed tests
   - Auto-generated recommendations

### Creating Custom Test Suites

Create a JSON file with this structure:

```json
{
  "name": "My Custom Suite",
  "description": "Description of what this suite tests",
  "config": {
    "tool_retrieval": {
      "limit": 2,
      "use_reranker": true,
      "use_embeddings": true,
      "primary_namespaces": [["tools"]],
      "fallback_namespaces": []
    },
    "scoring": {
      "route_correct_weight": 0.15,
      "sub_route_correct_weight": 0.10,
      "agent_correct_weight": 0.25,
      "exact_match_weight": 0.30,
      "acceptable_match_weight": 0.20
    },
    "test_routing": true,
    "test_agents": true
  },
  "categories": [
    {
      "category_id": "my_category",
      "category_name": "My Category",
      "test_cases": [
        {
          "id": "test_001",
          "query": "User query text",
          "expected_route": "action",
          "expected_sub_route": "travel",
          "expected_agents": ["trafik", "action"],
          "expected_tools": ["trafikverket_trafikinfo_storningar"],
          "acceptable_tools": ["trafikverket_trafikinfo_storningar", "trafikverket_trafikinfo_koer"],
          "tags": ["störning", "väg"],
          "difficulty": "easy",
          "language": "sv"
        }
      ]
    }
  ]
}
```

### Interpreting Results

#### Metrics Explained

- **Tool Exact Rate** - Percentage of cases where selected tools exactly match expected
- **Tool Acceptable Rate** - Percentage where selected tools are within acceptable set
- **Composite Score** - Weighted score across all 4 layers (0.0 to 1.0)
- **Route Accuracy** - Percentage of correct route classifications
- **Agent Overlap** - Average Jaccard similarity for agent selection

#### When to Take Action

**Tool Exact Rate < 70%**
- Review tool metadata (keywords, example queries)
- Consider adjusting `TOOL_EMBEDDING_WEIGHT` in bigtool_store.py
- Check if reranker is working correctly

**Route Accuracy < 80%**
- Improve regex patterns in dispatcher.py
- Add more specific patterns for problematic routes

**Agent Exact Rate < 60%**
- Update agent descriptions and keywords
- Review agent selection scoring weights

**High Latency (> 500ms)**
- Check if embeddings are cached
- Review reranker performance
- Consider reducing `TOOL_RERANK_CANDIDATES`

### Cache Management

The tool index is cached for performance. Clear the cache after:
- Editing tool metadata in `/admin/tools`
- Adding new tools or tool definitions
- Changing tool keywords or descriptions

Click "Rensa Cache" button or call:
```bash
curl -X POST http://localhost:8000/api/v1/admin/tool-eval/invalidate-cache
```

## Development Guide

### Adding New Test Cases

1. Edit `eval_suites/full_pipeline_eval_v1.json`
2. Add test case to appropriate category
3. Include all relevant fields:
   - `id` - Unique identifier
   - `query` - User query text
   - `expected_route`, `expected_sub_route`, `expected_agents`, `expected_tools`
   - `acceptable_tools` - Acceptable alternatives
   - `tags` - For failure pattern analysis
   - `difficulty` - easy/medium/hard
   - `language` - sv/en

### Extending Evaluation Logic

To add new evaluation layers or metrics:

1. Edit `tool_eval_service.py`
2. Add new fields to `SingleResult` dataclass
3. Update `evaluate_single()` to compute new metrics
4. Update `run_evaluation()` to aggregate new metrics
5. Add new fields to `EvalReport` dataclass
6. Update frontend types in `admin-tool-eval.types.ts`
7. Update UI in `tool-eval-page.tsx` to display new metrics

### Testing Changes

Run validation tests:
```bash
cd surfsense_backend
python tests/test_tool_eval.py
```

## Troubleshooting

### Issue: No tools selected for query
- Check if query matches any tool keywords
- Verify namespace configuration
- Review semantic embedding scores

### Issue: Wrong route classification
- Check regex patterns in dispatcher.py
- Verify pattern order (earlier patterns take precedence)
- Test in single query tester to debug

### Issue: High latency
- Clear tool index cache
- Check embedding model performance
- Review reranker configuration

### Issue: All tests fail
- Verify tool definitions are imported correctly
- Check stub tool registry builder
- Ensure namespace mappings are correct

## Performance Considerations

- Tool index is built once and cached per session
- Embeddings are computed lazily and cached
- Reranking limited to top 24 candidates by default
- Average query latency should be < 200ms

## Security

- All endpoints require admin authentication
- Uses same `_require_admin` check as other admin routes
- No real API keys needed (uses stubs)
- No external API calls made during evaluation

## Future Enhancements

Potential improvements:

- [ ] Visual diff comparison between production and evaluation results
- [ ] Historical tracking of evaluation runs over time
- [ ] A/B testing different scoring configurations
- [ ] Automated regression testing on tool changes
- [ ] Export evaluation reports as PDF/CSV
- [ ] Integration with CI/CD pipeline
- [ ] Parallel evaluation for faster suite execution
- [ ] Tool metadata suggestions based on failures

## Related Files

### Backend
- `app/agents/new_chat/bigtool_store.py` - Tool index and retrieval logic
- `app/agents/new_chat/dispatcher.py` - Route classification patterns
- `app/agents/new_chat/knowledge_router.py` - Knowledge sub-routing
- `app/agents/new_chat/action_router.py` - Action sub-routing
- `app/agents/new_chat/supervisor_agent.py` - Agent selection logic

### Frontend
- `app/admin/layout.tsx` - Admin layout wrapper
- `components/admin/admin-layout.tsx` - Navigation sidebar
- `contracts/types/admin-tool-settings.types.ts` - Tool settings types

## Support

For issues or questions:
1. Check this documentation
2. Review test cases in `eval_suites/full_pipeline_eval_v1.json`
3. Run validation tests in `tests/test_tool_eval.py`
4. Check logs in backend for detailed error messages
