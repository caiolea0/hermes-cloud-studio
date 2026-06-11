# MCP Coverage Report — 2026-06

**Period**: 2026-06-01 to 2026-06-30  
**Generated**: 2026-06-11T10:25:56.044371Z

## Summary
- Total tools: 52
- **Active** (called last 7d): 0
- **Warning** (7-30d): 0
- **Orphan** (zero calls 30d): 21
- **Deprecated**: 0
- **Quarantine**: 0
- **Reserved**: 31
- **DRIFT DETECTED**: 21 WARN
- Total calls: 0 | Errors: 0 (0.00%)

## DRIFT DETECTED

| Server | Tool | Registry | Runtime | Reason |
|---|---|---|---|---|
| hermes-linkedin | get_health | active | orphan | registered active but zero calls 30d |
| hermes-linkedin | get_rate_limits | active | orphan | registered active but zero calls 30d |
| hermes-linkedin | get_warmup_status | active | orphan | registered active but zero calls 30d |
| hermes-linkedin | get_account_profile | active | orphan | registered active but zero calls 30d |
| hermes-linkedin | assert_account_safe | active | orphan | registered active but zero calls 30d |
| hermes-linkedin | preflight_check | active | orphan | registered active but zero calls 30d |
| hermes-linkedin | probe_cooldown | active | orphan | registered active but zero calls 30d |
| hermes-linkedin | start_campaign | active | orphan | registered active but zero calls 30d |
| hermes-prospects | search_prospects | active | orphan | registered active but zero calls 30d |
| hermes-prospects | score_lead | active | orphan | registered active but zero calls 30d |
| hermes-prospects | mark_converted | active | orphan | registered active but zero calls 30d |
| hermes-prospects | get_campaign_stats | active | orphan | registered active but zero calls 30d |
| hermes-prospects | enrich_pipeline | active | orphan | registered active but zero calls 30d |
| hermes-prospects | list_top_scored | active | orphan | registered active but zero calls 30d |
| hermes-prospects | get_by_status | active | orphan | registered active but zero calls 30d |
| hermes-skills | list_skills | active | orphan | registered active but zero calls 30d |
| hermes-skills | get_skill | active | orphan | registered active but zero calls 30d |
| hermes-skills | toggle_active | active | orphan | registered active but zero calls 30d |
| hermes-skills | propose_skill_yaml_stub | active | orphan | registered active but zero calls 30d |
| hermes-skills | test_skill_dryrun | active | orphan | registered active but zero calls 30d |
| hermes-skills | get_metrics | active | orphan | registered active but zero calls 30d |

## Tier Breakdown

| Server | Tool | Tier | Calls | Avg ms | Errors | Last Call |
|---|---|---|---|---|---|---|
| filesystem | list_directory | reserved | 0 | - | 0 | - |
| filesystem | read_file | reserved | 0 | - | 0 | - |
| filesystem | write_file | reserved | 0 | - | 0 | - |
| git | git_diff | reserved | 0 | - | 0 | - |
| git | git_log | reserved | 0 | - | 0 | - |
| git | git_show | reserved | 0 | - | 0 | - |
| git | git_status | reserved | 0 | - | 0 | - |
| github | create_issue | reserved | 0 | - | 0 | - |
| github | create_pull_request | reserved | 0 | - | 0 | - |
| github | get_pr | reserved | 0 | - | 0 | - |
| github | list_pull_requests | reserved | 0 | - | 0 | - |
| github | merge_pr | reserved | 0 | - | 0 | - |
| hermes-linkedin | assert_account_safe | orphan | 0 | - | 0 | - |
| hermes-linkedin | get_account_profile | orphan | 0 | - | 0 | - |
| hermes-linkedin | get_health | orphan | 0 | - | 0 | - |
| hermes-linkedin | get_rate_limits | orphan | 0 | - | 0 | - |
| hermes-linkedin | get_warmup_status | orphan | 0 | - | 0 | - |
| hermes-linkedin | preflight_check | orphan | 0 | - | 0 | - |
| hermes-linkedin | probe_cooldown | orphan | 0 | - | 0 | - |
| hermes-linkedin | start_campaign | orphan | 0 | - | 0 | - |
| hermes-prospects | enrich_pipeline | orphan | 0 | - | 0 | - |
| hermes-prospects | get_by_status | orphan | 0 | - | 0 | - |
| hermes-prospects | get_campaign_stats | orphan | 0 | - | 0 | - |
| hermes-prospects | list_top_scored | orphan | 0 | - | 0 | - |
| hermes-prospects | mark_converted | orphan | 0 | - | 0 | - |
| hermes-prospects | score_lead | orphan | 0 | - | 0 | - |
| hermes-prospects | search_prospects | orphan | 0 | - | 0 | - |
| hermes-skills | get_metrics | orphan | 0 | - | 0 | - |
| hermes-skills | get_skill | orphan | 0 | - | 0 | - |
| hermes-skills | list_skills | orphan | 0 | - | 0 | - |
| hermes-skills | propose_skill_yaml_stub | orphan | 0 | - | 0 | - |
| hermes-skills | test_skill_dryrun | orphan | 0 | - | 0 | - |
| hermes-skills | toggle_active | orphan | 0 | - | 0 | - |
| hunter | domain_search | reserved | 0 | - | 0 | - |
| hunter | email_finder | reserved | 0 | - | 0 | - |
| hunter | verify_email | reserved | 0 | - | 0 | - |
| omnisearch | fetch_firecrawl | reserved | 0 | - | 0 | - |
| omnisearch | search_brave | reserved | 0 | - | 0 | - |
| omnisearch | search_exa | reserved | 0 | - | 0 | - |
| omnisearch | search_kagi | reserved | 0 | - | 0 | - |
| playwright_ms | browser_click | reserved | 0 | - | 0 | - |
| playwright_ms | browser_navigate | reserved | 0 | - | 0 | - |
| playwright_ms | browser_screenshot | reserved | 0 | - | 0 | - |
| playwright_ms | browser_snapshot | reserved | 0 | - | 0 | - |
| postgres | describe_table | reserved | 0 | - | 0 | - |
| postgres | execute | reserved | 0 | - | 0 | - |
| postgres | list_schemas | reserved | 0 | - | 0 | - |
| postgres | query | reserved | 0 | - | 0 | - |
| sentry | capture_exception | reserved | 0 | - | 0 | - |
| sentry | list_issues | reserved | 0 | - | 0 | - |
| sentry | resolve_issue | reserved | 0 | - | 0 | - |
| sentry | trigger_seer_root_cause | reserved | 0 | - | 0 | - |

## Index Health
OK idx_mcp_calls_server_tool_time used by aggregate query
