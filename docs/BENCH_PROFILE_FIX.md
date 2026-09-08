# Bench-Tricorder Profile Fix Log
Date: 2026-08-29

## Root Cause
Variant A recorded 0 tricorder tool calls because the `bench-tricorder` profile config lacked the `mcp_servers:` block, so Hermes did not spawn or connect to the `tricorder-mcp.exe` server for profile sessions.

## Fix Applied
Added the missing `mcp_servers` block to `C:\Users\macdo\AppData\Local\hermes\profiles\bench-tricorder\config.yaml`:

```yaml
mcp_servers:
  tricorder:
    args: []
    command: D:\Projects\tricorder\.venv\Scripts\tricorder-mcp.exe
```

Also restored `-s codebase-tricorder` in `bench/bench_agent_eval.py` to match the profile skill slug.

## Verification
Forced chat test (`force_tc.txt`) confirmed `mcp__tricorder__tricorder_detect` successfully executed and returned `PCM::AddToBuffer` from `src/libprojectM/Audio/PCM.cpp`.
