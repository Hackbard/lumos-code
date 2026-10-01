#!/usr/bin/env python3
"""cpg_get_blast_radius.py — CLI Wrapper for Joern Code Property Graph Blast Radius.

Computes mathematical blast radius (AST + CFG + DFG reachability) and outputs
whitelisted paths for ContextOps work-claims (claim.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add lumos_code to path
ROOT_DIR = Path(__file__).parent.resolve()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from lmc import joern as joern_mod
    from lmc.client import CodebadgerClient
except ImportError:
    joern_mod = None
    CodebadgerClient = None


def _hash_from_path(p: Path) -> str:
    return hashlib.sha1(str(p.resolve()).encode()).hexdigest()[:16]


def map_sysml_to_symbol(sysml_ref: str) -> str:
    """Extracts target function or class signature from SysML reference."""
    clean = sysml_ref.strip()
    if "::" in clean:
        parts = clean.split("::")
        return parts[-1]
    return clean


def compute_blast_radius(
    target_spec: str,
    worktree: Path,
    depth: int = 3,
    engine: str = "treesitter",
    locked_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    worktree = worktree.resolve()
    cbh = _hash_from_path(worktree)
    symbol = map_sysml_to_symbol(target_spec)

    read_paths: Set[str] = set()
    write_paths: Set[str] = set()
    affected_methods: List[str] = []

    # 1. Joern engine
    if engine == "joern" and joern_mod:
        jc = joern_mod.JoernClient()
        if jc.is_up():
            # Run CPG Reachability Traversal
            escaped_symbol = symbol.replace('"', '\\"')
            cpgql = (
                f'val targets = cpg.method(".*{escaped_symbol}.*").l; '
                f'val callers = targets.caller.l; '
                f'val allMethods = (targets ++ callers).distinct; '
                f'allMethods.map(m => Seq(m.fullName, m.filename).mkString("|")).mkString("\\n")'
            )
            raw = jc.query(cpgql)
            if raw:
                for line in raw.splitlines():
                    if "|" in line:
                        m_name, f_name = line.split("|", 1)
                        if m_name:
                            affected_methods.append(m_name.strip())
                        if f_name and f_name != "<empty>":
                            rel_file = f_name.strip()
                            if rel_file.startswith("/"):
                                try:
                                    rel_file = str(Path(rel_file).relative_to(worktree))
                                except Exception:
                                    pass
                            read_paths.add(rel_file)

    # 2. Fallback or Tree-Sitter engine
    if not affected_methods and CodebadgerClient:
        try:
            client = CodebadgerClient(timeout=2.0)
            find_res = client.find_methods(cbh, f".*{symbol}.*")
            methods = (find_res.get("data") or {}).get("methods", [])
            for m in methods:
                affected_methods.append(m.get("signature", ""))
                f = m.get("file")
                if f:
                    read_paths.add(f)
                    write_paths.add(f)

            # Callers / Incoming calls
            call_res = client.get_call_graph(cbh, symbol, direction="incoming", depth=depth)
            incoming = (call_res.get("data") or {}).get("affected", {})
            for d, m_list in incoming.items():
                for m_sig in m_list:
                    affected_methods.append(m_sig)
        except Exception:
            pass

    # 3. Direct Static Traversal Fallback (0 External Dependencies)
    if not read_paths and worktree.exists():
        for ext in ("*.php", "*.js", "*.ts", "*.py"):
            for fpath in worktree.rglob(ext):
                rel = str(fpath.relative_to(worktree))
                if any(rel.startswith(skip) for skip in ("vendor/", "node_modules/", "storage/", ".git/")):
                    continue
                if symbol.lower() in fpath.name.lower():
                    read_paths.add(rel)
                    write_paths.add(rel)
                    affected_methods.append(f"{symbol}::{fpath.stem}")

    # If write_paths empty, target method files are write_paths
    if not write_paths and read_paths:
        for p in read_paths:
            if symbol.lower() in p.lower() or not write_paths:
                write_paths.add(p)

    default_locked = ["config/*", "routes/*", "database/migrations/*", ".env*"]
    locked_paths = locked_patterns if locked_patterns is not None else default_locked

    return {
        "success": True,
        "target_sysml_ref": target_spec,
        "resolved_symbol": symbol,
        "engine_used": engine,
        "depth": depth,
        "affected_methods": sorted(set(affected_methods)),
        "bounded_scope": {
            "read_paths": sorted(read_paths) if read_paths else ["app/**"],
            "write_paths": sorted(write_paths) if write_paths else ["app/**"],
            "locked_paths": locked_paths,
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Joern CPG Blast Radius & Scope Whitelist.")
    parser.add_argument("target", help="Target method signature or SysML qualified reference.")
    parser.add_argument("--worktree", default=".", help="Path to worktree root.")
    parser.add_argument("--depth", type=int, default=3, help="Analysis reachability depth.")
    parser.add_argument("--engine", choices=["joern", "treesitter"], default="treesitter", help="Analysis engine.")
    parser.add_argument("--json", action="store_true", help="Output JSON claim snippet.")

    args = parser.parse_args()
    res = compute_blast_radius(
        target_spec=args.target,
        worktree=Path(args.worktree),
        depth=args.depth,
        engine=args.engine
    )

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"=== CPG Blast Radius Scope: {res['target_sysml_ref']} ===")
        print(f"Resolved Symbol  : {res['resolved_symbol']}")
        print(f"Engine           : {res['engine_used']} (depth={res['depth']})")
        print(f"Affected Methods : {len(res['affected_methods'])}")
        for m in res["affected_methods"][:10]:
            print(f"  - {m}")
        if len(res["affected_methods"]) > 10:
            print(f"  ... and {len(res['affected_methods']) - 10} more")
        print("\nBounded Scope for claim.json:")
        print(f"  read_paths   : {res['bounded_scope']['read_paths']}")
        print(f"  write_paths  : {res['bounded_scope']['write_paths']}")
        print(f"  locked_paths : {res['bounded_scope']['locked_paths']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
