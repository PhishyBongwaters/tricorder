#!/usr/bin/env python3
"""
Tricorder Python Client

Programmatic client for tricorder repository mapping.
Used by dsh for turn-0 T0 map injection and other integrations.

Usage:
    from tricorder_client import TricorderClient
    
    client = TricorderClient()
    map_text = client.scan("/path/to/repo", token_limit=2048)
    result = client.detect("/path/to/repo", "MyClass::method")
"""

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class ScanResult:
    """Result from tricorder_scan."""
    map: str
    token_estimate: int
    full_repo_estimate: int
    savings_pct: float
    report: dict


@dataclass
class DetectResult:
    """Result from tricorder_detect."""
    results: list[dict]
    token_estimate: int
    full_repo_estimate: int
    savings_pct: float


class TricorderClient:
    """
    Programmatic client for tricorder.
    
    Uses the tricorder CLI (tricorder.exe) for scan operations
    and can be extended to use MCP for detect/symbols/detail.
    """
    
    def __init__(
        self,
        tricorder_exe: Optional[str] = None,
        default_token_limit: int = 8192,
    ):
        """
        Initialize client.
        
        Args:
            tricorder_exe: Path to tricorder executable. Auto-detected if None.
            default_token_limit: Default token limit for scans.
        """
        self.default_token_limit = default_token_limit
        
        if tricorder_exe is None:
            # Auto-detect common locations
            candidates = [
                Path(r"D:\Projects\tricorder\.venv\Scripts\tricorder.exe"),
                Path.home() / "AppData" / "Roaming" / "Python" / "Python314" / "Scripts" / "tricorder.exe",
                Path("tricorder.exe"),  # on PATH
            ]
            for c in candidates:
                if c.exists():
                    self.tricorder_exe = str(c)
                    break
            else:
                self.tricorder_exe = "tricorder"  # fallback to PATH
        else:
            self.tricorder_exe = tricorder_exe
    
    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run tricorder CLI with given args."""
        return subprocess.run(
            [self.tricorder_exe, *args],
            capture_output=True,
            text=True,
            timeout=120,
        )
    
    def scan(
        self,
        project_root: str,
        scan_path: Optional[str] = None,
        token_limit: Optional[int] = None,
        tier: int = 0,
        exclude_untagged: bool = True,
        exclude_globs: Optional[list[str]] = None,
        output_format: str = "text",
    ) -> ScanResult:
        """
        Generate a repository map (T0 or T1).
        
        Args:
            project_root: Absolute path to project root.
            scan_path: Specific path to scan (relative to root or absolute).
            token_limit: Maximum tokens for map (default: 8192).
            tier: 0 = definitions only, 1 = definitions + context.
            exclude_untagged: Skip untagged files section.
            exclude_globs: Glob patterns to exclude from scan.
            output_format: "text" or "mermaid".
        
        Returns:
            ScanResult with map text and metadata.
        """
        args = [
            "--root", project_root,
            "--map-tokens", str(token_limit or self.default_token_limit),
            "--tier", str(tier),
            "--format", output_format,
        ]
        if exclude_untagged:
            args.append("--exclude-untagged")
        if exclude_globs:
            args.extend(["--exclude-globs", *exclude_globs])
        if scan_path:
            args.append(scan_path)
        
        result = self._run(args)
        
        # Parse output for token estimate and coverage
        token_estimate = 0
        coverage_pct = 0.0
        full_repo = 0
        
        output = result.stdout + "\n" + result.stderr
        for line in output.split("\n"):
            if "Repo-map:" in line and "k-tokens" in line:
                m = re.search(r"Repo-map:\s*([\d.]+)\s*k-tokens", line)
                if m:
                    token_estimate = int(float(m.group(1)) * 1024)
            elif "Repo-map:" in line and "tokens" in line:
                m = re.search(r"Repo-map:\s*(\d+)\s*tokens", line)
                if m:
                    token_estimate = int(m.group(1))
            elif "Low map coverage:" in line:
                m = re.search(r"Low map coverage: (\d+)/(\d+) source files \(([\d.]+)%\)", line)
                if m:
                    coverage_pct = float(m.group(3))
        
        # Get full repo estimate
        stats_result = self._run(["--root", project_root, "--stats-only"])
        try:
            full_repo = json.loads(stats_result.stdout).get("full_repo_estimate", 0)
        except Exception:
            full_repo = 0
        
        if token_estimate == 0:
            token_estimate = len(result.stdout) // 4  # rough fallback
        
        savings = max(0.0, 1 - token_estimate / full_repo) * 100 if full_repo else 0.0
        
        return ScanResult(
            map=result.stdout,
            token_estimate=token_estimate,
            full_repo_estimate=full_repo,
            savings_pct=round(savings, 1),
            report={"coverage_pct": coverage_pct},
        )
    
    def detect(
        self,
        project_root: str,
        query: str,
        max_results: int = 50,
        include_definitions: bool = True,
        include_references: bool = False,
    ) -> DetectResult:
        """
        Search for an identifier (uses MCP server if available, falls back to CLI scan + filter).
        
        Note: Full detect requires MCP server. This fallback scans and filters locally.
        """
        # For now, use scan + filter as fallback
        # A real implementation would call the MCP tricorder_detect tool
        scan_result = self.scan(project_root, token_limit=8192, tier=0)
        
        # Simple substring filter on map output
        query_lower = query.lower()
        results = []
        
        for line in scan_result.map.split("\n"):
            if query_lower in line.lower() and ":" in line:
                # Try to parse file:line format
                parts = line.strip().split(":", 2)
                if len(parts) >= 2:
                    try:
                        file_part = parts[0].strip()
                        line_part = int(parts[1].strip().split()[0]) if parts[1].strip() else 1
                        name = query
                        results.append({
                            "file": file_part,
                            "line": line_part,
                            "name": name,
                            "kind": "def",
                            "context": line.strip(),
                        })
                    except (ValueError, IndexError):
                        pass
        
        results = results[:max_results]
        tok = len(json.dumps(results)) // 4
        full_repo = scan_result.full_repo_estimate
        
        return DetectResult(
            results=results,
            token_estimate=tok,
            full_repo_estimate=full_repo,
            savings_pct=round(max(0.0, 1 - tok / full_repo) * 100, 1) if full_repo else 0.0,
        )


class TricorderMCPClient:
    """
    Async client for tricorder MCP server.
    
    Requires tricorder-mcp.exe to be running as an MCP server.
    This is the preferred interface for dsh integration.
    """
    
    def __init__(self, mcp_command: Optional[list[str]] = None):
        """
        Initialize MCP client.
        
        Args:
            mcp_command: Command to start tricorder-mcp server.
                        Default: ["tricorder-mcp"] (assumes on PATH)
        """
        self.mcp_command = mcp_command or [
            r"C:\Users\macdo\AppData\Roaming\Python\Python314\Scripts\tricorder-mcp.exe"
        ]
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
    
    async def start(self) -> None:
        """Start the MCP server process."""
        if self._process is None:
            self._process = await asyncio.create_subprocess_exec(
                *self.mcp_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
    
    async def stop(self) -> None:
        """Stop the MCP server process."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None
    
    async def _call(self, method: str, params: dict) -> dict:
        """Call an MCP tool."""
        await self.start()
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {"name": method, "arguments": params},
        }
        request_json = json.dumps(request) + "\n"
        self._process.stdin.write(request_json.encode())
        await self._process.stdin.drain()
        
        line = await self._process.stdout.readline()
        response = json.loads(line.decode())
        
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response.get("result", {})
    
    async def scan(self, project_root: str, **kwargs) -> ScanResult:
        """Call tricorder_scan via MCP."""
        result = await self._call("tricorder_scan", {"project_root": project_root, **kwargs})
        return ScanResult(
            map=result.get("map", ""),
            token_estimate=result.get("token_estimate", 0),
            full_repo_estimate=result.get("full_repo_estimate", 0),
            savings_pct=result.get("savings_pct", 0.0),
            report=result.get("report", {}),
        )
    
    async def detect(self, project_root: str, query: str, **kwargs) -> DetectResult:
        """Call tricorder_detect via MCP."""
        result = await self._call("tricorder_detect", {"project_root": project_root, "query": query, **kwargs})
        return DetectResult(
            results=result.get("results", []),
            token_estimate=result.get("token_estimate", 0),
            full_repo_estimate=result.get("full_repo_estimate", 0),
            savings_pct=result.get("savings_pct", 0.0),
        )
    
    async def symbols(self, project_root: str, query: str = "", **kwargs) -> dict:
        """Call tricorder_symbols via MCP."""
        return await self._call("tricorder_symbols", {"project_root": project_root, "query": query, **kwargs})
    
    async def detail(self, project_root: str, name: str, file: str, line: int) -> dict:
        """Call tricorder_detail via MCP."""
        return await self._call("tricorder_detail", {"project_root": project_root, "name": name, "file": file, "line": line})


# Convenience function for turn-0 injection
def inject_turn0_map(session, project_root: str, token_limit: int = 2048) -> bool:
    """
    Inject T0 map into a session at turn 0.
    
    Args:
        session: dsh Session object (must have .events, .header.cwd, .append())
        project_root: Absolute path to project root.
        token_limit: Token budget for T0 map.
    
    Returns:
        True if injection succeeded, False otherwise.
    """
    # Check if already past turn 0
    if any(e.type == "turn/start" for e in session.events):
        return False
    
    cwd = session.header.cwd or project_root
    if not cwd:
        return False
    
    try:
        client = TricorderClient()
        result = client.scan(cwd, token_limit=token_limit, tier=0, exclude_untagged=True)
        
        if not result.map.strip():
            return False
        
        # Inject as plugin-sourced user message (appears in model surface)
        session.append("user/message", {
            "content": [{"type": "text", "text": f"[tricorder] {result.map}"}],
            "source": {"kind": "plugin", "plugin": "tricorder"},
        }, {"surfaceOp": "append"})
        
        return True
    except Exception:
        return False


# Async version for MCP
async def inject_turn0_map_async(session, project_root: str, token_limit: int = 2048) -> bool:
    """Async version using MCP client."""
    if any(e.type == "turn/start" for e in session.events):
        return False
    
    cwd = session.header.cwd or project_root
    if not cwd:
        return False
    
    try:
        client = TricorderMCPClient()
        result = await client.scan(cwd, token_limit=token_limit, tier=0, exclude_untagged=True)
        await client.stop()
        
        if not result.map.strip():
            return False
        
        session.append("user/message", {
            "content": [{"type": "text", "text": f"[tricorder] {result.map}"}],
            "source": {"kind": "plugin", "plugin": "tricorder"},
        }, {"surfaceOp": "append"})
        
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # Demo
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    client = TricorderClient()
    result = client.scan(root, token_limit=2048)
    print(f"Tokens: {result.token_estimate}/{result.full_repo_estimate} ({result.savings_pct}% savings)")
    print(result.map[:2000])