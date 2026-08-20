#!/usr/bin/env python3
"""
Tricorder Turn-0 Injection for DeepSeek Harness (dsh)

This module provides the turn-0 T0 map injection logic that can be
used as a dsh plugin. It hooks into session creation and injects
a repository map before the first turn starts.

dsh Plugin Integration:
=======================

1. Add to your dsh profile's cordis.patch.yml:

```yaml
- insert:
    - id: tricorder-inject
      name: '@deepseek-ai/dsh-tricorder-inject'
      config:
        token_limit: 2048
        exclude_globs:
          - "vendor/**"
          - "third_party/**"
        use_mcp: false
```

2. The plugin will automatically:
   - Listen for `session/created` events (global)
   - Check if session is at turn 0 (no turn/start event)
   - Generate T0 map for session's cwd
   - Inject as plugin-sourced user/message (appears in model surface)

MCP vs CLI:
===========
- use_mcp: false (default) - uses tricorder CLI, simpler, no extra wiring
- use_mcp: true - uses tricorder-mcp MCP server, structured JSON, token estimates

Requirements:
=============
- tricorder CLI installed (pip install -e D:/Projects/tricorder)
- OR tricorder-mcp.exe for MCP mode
"""

import asyncio
from pathlib import Path
from typing import Optional

try:
    from cordis import Context, Service
    from cordis.core.events import Event
except ImportError:
    # Fallback types for standalone use
    class Context:
        pass
    class Service:
        pass
    class Event:
        pass

try:
    from dsh_session import Session, SessionId
except ImportError:
    class Session:
        events: list
        header: any
        def append(self, *args, **kwargs): pass
    class SessionId:
        def __init__(self, v): self.value = v


class TricorderInjectConfig:
    """Configuration for tricorder injection plugin."""
    
    def __init__(
        self,
        token_limit: int = 2048,
        scan_path: Optional[str] = None,
        exclude_globs: Optional[list[str]] = None,
        use_mcp: bool = False,
        mcp_command: Optional[list[str]] = None,
        verbose: bool = False,
    ):
        self.token_limit = token_limit
        self.scan_path = scan_path
        self.exclude_globs = exclude_globs or []
        self.use_mcp = use_mcp
        self.mcp_command = mcp_command
        self.verbose = verbose


class TricorderInjector:
    """
    Turn-0 T0 map injector for dsh sessions.
    
    This is the core injection logic, usable both as a Cordis service
    and as a standalone function.
    """
    
    def __init__(self, config: TricorderInjectConfig):
        self.config = config
        self._cli_client = None
        self._mcp_client = None
    
    def _get_cli_client(self):
        """Lazy-init CLI client."""
        if self._cli_client is None:
            from tricorder_client import TricorderClient
            self._cli_client = TricorderClient()
        return self._cli_client
    
    async def _get_mcp_client(self):
        """Lazy-init MCP client."""
        if self._mcp_client is None:
            from tricorder_client import TricorderMCPClient
            self._mcp_client = TricorderMCPClient(self.config.mcp_command)
        return self._mcp_client
    
    def inject_sync(self, session: Session) -> bool:
        """
        Synchronous injection using CLI.
        
        Called from session/created listener.
        """
        # Guard: only inject at turn 0
        if any(getattr(e, "type", None) == "turn/start" for e in session.events):
            if self.config.verbose:
                print(f"[tricorder-inject] Session {session.id}: not turn 0, skipping")
            return False
        
        cwd = getattr(session.header, "cwd", None)
        if not cwd:
            if self.config.verbose:
                print(f"[tricorder-inject] Session {session.id}: no cwd, skipping")
            return False
        
        try:
            client = self._get_cli_client()
            result = client.scan(
                cwd,
                scan_path=self.config.scan_path,
                token_limit=self.config.token_limit,
                tier=0,
                exclude_untagged=True,
                exclude_globs=self.config.exclude_globs or None,
            )
            
            if not result.map.strip():
                if self.config.verbose:
                    print(f"[tricorder-inject] Session {session.id}: empty map")
                return False
            
            # Inject as plugin-sourced message
            session.append("user/message", {
                "content": [{"type": "text", "text": f"[tricorder] {result.map}"}],
                "source": {"kind": "plugin", "plugin": "tricorder"},
            }, {"surfaceOp": "append"})
            
            if self.config.verbose:
                print(f"[tricorder-inject] Session {session.id}: injected T0 map "
                      f"({result.token_estimate} tokens, {result.savings_pct}% savings)")
            return True
            
        except Exception as e:
            if self.config.verbose:
                print(f"[tricorder-inject] Session {session.id}: error: {e}")
            return False
    
    async def inject_async(self, session: Session) -> bool:
        """
        Async injection using MCP.
        
        Called from session/created listener (async).
        """
        if any(getattr(e, "type", None) == "turn/start" for e in session.events):
            return False
        
        cwd = getattr(session.header, "cwd", None)
        if not cwd:
            return False
        
        try:
            client = await self._get_mcp_client()
            result = await client.scan(
                cwd,
                token_limit=self.config.token_limit,
                tier=0,
                exclude_untagged=True,
                exclude_globs=self.config.exclude_globs or None,
            )
            
            if not result.map.strip():
                return False
            
            session.append("user/message", {
                "content": [{"type": "text", "text": f"[tricorder] {result.map}"}],
                "source": {"kind": "plugin", "plugin": "tricorder"},
            }, {"surfaceOp": "append"})
            
            return True
        except Exception:
            return False
        finally:
            # Don't stop MCP client here - reuse across sessions
            pass


# Cordis Service wrapper
class TricorderInjectService(Service):
    """
    Cordis service for tricorder turn-0 injection.
    
    Registers global listener on session/created.
    """
    
    inject = ["sessions"]
    
    def __init__(self, ctx: Context, config: TricorderInjectConfig):
        super().__init__(ctx, "tricorderInject")
        self.config = config
        self.injector = TricorderInjector(config)
        
        # Seed existing sessions
        for session in ctx.sessions.list():
            self._inject_session(session)
        
        # Hook new sessions (global = all scopes)
        ctx.on("session/created", self._inject_session, {"global": True})
    
    def _inject_session(self, session: Session) -> None:
        """Inject map into session (sync)."""
        if self.config.use_mcp:
            # Schedule async injection
            asyncio.create_task(self.injector.inject_async(session))
        else:
            self.injector.inject_sync(session)


# Export for Cordis plugin registration
def apply(ctx: Context, config: Optional[dict] = None):
    """
    Cordis plugin entry point.
    
    Usage in cordis.yml:
        - name: tricorder-inject
          config:
            token_limit: 2048
            exclude_globs:
              - "vendor/**"
    """
    cfg = TricorderInjectConfig(**(config or {}))
    service = TricorderInjectService(ctx, cfg)
    return service


# Standalone function for manual use
def inject_turn0_map(
    session: Session,
    project_root: str,
    token_limit: int = 2048,
    exclude_globs: Optional[list[str]] = None,
    use_mcp: bool = False,
) -> bool:
    """
    Manually inject T0 map into a session.
    
    Useful for testing or non-Cordis contexts.
    """
    config = TricorderInjectConfig(
        token_limit=token_limit,
        exclude_globs=exclude_globs,
        use_mcp=use_mcp,
    )
    injector = TricorderInjector(config)
    
    # Temporarily override session header cwd
    original_cwd = getattr(session.header, "cwd", None)
    session.header.cwd = project_root
    try:
        if use_mcp:
            return asyncio.run(injector.inject_async(session))
        else:
            return injector.inject_sync(session)
    finally:
        if original_cwd is not None:
            session.header.cwd = original_cwd


if __name__ == "__main__":
    # Demo: create a mock session and inject
    class MockSession:
        def __init__(self, cwd):
            self.events = []
            self.header = type("Header", (), {"cwd": cwd})()
            self.id = "test-session"
            self.appended = []
        
        def append(self, event_type, data, opts=None):
            self.appended.append((event_type, data, opts))
            print(f"Appended: {event_type} - {data['content'][0]['text'][:100]}...")
    
    import sys
    cwd = sys.argv[1] if len(sys.argv) > 1 else "."
    # For projectm, scan path is src/libprojectM
    scan_path = sys.argv[2] if len(sys.argv) > 2 else None
    session = MockSession(cwd)
    
    config = TricorderInjectConfig(token_limit=2048, scan_path=scan_path, verbose=True)
    injector = TricorderInjector(config)
    success = injector.inject_sync(session)
    
    print(f"Injection {'succeeded' if success else 'failed'}")