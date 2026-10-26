#!/usr/bin/env python3
"""Read-only repository inventory for DiffProof; never runs project checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

VERSION = "0.1.0"
CHECK_NAMES = {"check", "test", "tests", "lint", "typecheck", "type-check", "build", "verify", "validate"}
REVIEW_WORDS = re.compile(r"\b(deploy|publish|release|migrat(?:e|ion)|seed|destroy|clean|upload|format|install)\b", re.I)
RISKY_SCRIPT_NAMES = {"deploy", "publish", "release", "migrate", "migration", "seed", "clean", "format", "install"}
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "vendor", "target", "dist", "build", ".venv", "venv", "__pycache__", ".next", ".tox"}
MANIFEST_NAMES = {"package.json", "go.mod", "pyproject.toml", "Cargo.toml", "Makefile"}


def classify_observation(
    *,
    launched: bool,
    exit_code: Optional[int] = None,
    skip_reason: Optional[str] = None,
    launch_error: Optional[str] = None,
) -> dict[str, Any]:
    """Map observed execution facts to a non-inflated status."""
    if skip_reason:
        return {"status": "SKIPPED", "reason": skip_reason}
    if launch_error:
        return {"status": "NOT RUN", "reason": launch_error}
    if not launched:
        return {"status": "NOT RUN", "reason": "The check was not attempted."}
    if exit_code is None:
        return {"status": "UNKNOWN", "reason": "The check started, but no exit status is available."}
    if exit_code == 0:
        return {"status": "PASS", "exit_code": 0}
    return {"status": "FAIL", "exit_code": exit_code}


def _run_git(root: Path, args: list[str], timeout: int = 12) -> dict[str, Any]:
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except FileNotFoundError:
        return {"started": False, "error": "Git executable is unavailable."}
    except subprocess.TimeoutExpired:
        return {"started": True, "timeout": True, "returncode": None, "stdout": "", "stderr": "Git inspection timed out."}
    except OSError as exc:
        return {"started": False, "error": f"Git could not be started: {type(exc).__name__}."}
    return {
        "started": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr[:2000],
    }


def _safe_read(root: Path, relative: str, limit: int = 1_000_000) -> Optional[str]:
    path = root / relative
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.stat().st_size > limit:
            return None
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError, RuntimeError):
        return None


def _risk_flags(script_name: str, definition: str) -> list[str]:
    flags: list[str] = []
    if script_name.lower() in RISKY_SCRIPT_NAMES or REVIEW_WORDS.search(definition):
        flags.append("inspect-script-for-side-effects")
    if script_name.lower() in {"pretest", "posttest", "precheck", "postcheck"}:
        flags.append("inspect-lifecycle-hooks")
    return flags


def _candidate(ecosystem: str, command: str, evidence: str, risk_flags: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "ecosystem": ecosystem,
        "command_candidate": command,
        "evidence": evidence,
        "status": "NOT RUN",
        "risk_flags": risk_flags or [],
    }


def _find_manifests(root: Path) -> tuple[list[str], bool]:
    """Find common manifests in a bounded, symlink-safe monorepo walk."""
    found: list[str] = []
    visited = 0
    truncated = False
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        dirs[:] = sorted(
            name for name in dirs
            if name.lower() not in SKIP_DIRS and not (current_path / name).is_symlink()
        )
        visited += 1
        if visited > 5000:
            truncated = True
            dirs[:] = []
            continue
        if depth >= 6:
            dirs[:] = []
        for name in sorted(set(files) & MANIFEST_NAMES):
            path = current_path / name
            try:
                if path.resolve(strict=True).is_relative_to(root) and path.is_file():
                    found.append(path.relative_to(root).as_posix())
                else:
                    found.append(path.relative_to(root).as_posix())
            except (OSError, RuntimeError):
                found.append(path.relative_to(root).as_posix())
    return sorted(set(found)), truncated


def discover_candidates(root: Path) -> dict[str, Any]:
    """Find configured checks without executing them or exposing script bodies."""
    root = root.resolve()
    manifest_paths, walk_truncated = _find_manifests(root)
    manifests = list(manifest_paths)
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = ["Manifest search limit reached; some nested project files may not be listed."] if walk_truncated else []

    for relative_manifest in manifest_paths:
        project_root = (root / relative_manifest).parent
        if relative_manifest == "package.json" or relative_manifest.endswith("/package.json"):
            package_text = _safe_read(root, relative_manifest)
            if package_text is None:
                warnings.append(f"{relative_manifest} could not be read safely; ignored.")
                continue
            try:
                package = json.loads(package_text)
                scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
                manager = str(package.get("packageManager", "npm")).split("@", 1)[0] if isinstance(package, dict) else "npm"
                if manager not in {"npm", "pnpm", "yarn", "bun"}:
                    manager = "npm"
                if not isinstance(scripts, dict):
                    warnings.append(f"{relative_manifest} scripts is not an object; no script candidates were read.")
                else:
                    for name, definition in scripts.items():
                        if isinstance(name, str) and name.lower() in CHECK_NAMES and isinstance(definition, str):
                            evidence = f"{relative_manifest}:scripts.{name}"
                            candidates.append(_candidate("Node.js", f"{manager} run {name}", evidence, _risk_flags(name, definition)))
                            for hook in (f"pre{name}", f"post{name}"):
                                if hook in scripts:
                                    candidates[-1]["risk_flags"].append("inspect-lifecycle-hooks")
            except (json.JSONDecodeError, AttributeError):
                warnings.append(f"{relative_manifest} is malformed; it was not used to propose commands.")
        elif relative_manifest == "go.mod" or relative_manifest.endswith("/go.mod"):
            if _safe_read(root, relative_manifest) is None:
                warnings.append(f"{relative_manifest} could not be read safely; ignored.")
                continue
            for name, command in (("tests", "go test ./..."), ("vet", "go vet ./..."), ("build", "go build ./...")):
                candidates.append(_candidate("Go", command, f"{relative_manifest} ({name} candidate; inspect repository CI first)"))
        elif relative_manifest == "pyproject.toml" or relative_manifest.endswith("/pyproject.toml"):
            pyproject = _safe_read(root, relative_manifest)
            if pyproject is None:
                warnings.append(f"{relative_manifest} could not be read safely; ignored.")
                continue
            lower = pyproject.lower()
            if "[tool.pytest" in lower or (project_root / "pytest.ini").is_file() or (project_root / "tests").is_dir():
                candidates.append(_candidate("Python", "python -m pytest", f"{relative_manifest} or tests/ (candidate; confirm test runner exists)"))
            if "[tool.ruff" in lower:
                candidates.append(_candidate("Python", "ruff check .", f"{relative_manifest}:[tool.ruff]"))
            if "[tool.mypy" in lower:
                candidates.append(_candidate("Python", "mypy .", f"{relative_manifest}:[tool.mypy]"))
            if "[build-system]" in lower:
                candidates.append(_candidate("Python", "python -m build", f"{relative_manifest}:[build-system] (inspect build requirements first)"))
        elif relative_manifest == "Cargo.toml" or relative_manifest.endswith("/Cargo.toml"):
            cargo = _safe_read(root, relative_manifest)
            if cargo is None:
                warnings.append(f"{relative_manifest} could not be read safely; ignored.")
                continue
            cargo_lower = cargo.lower()
            candidates.append(_candidate("Rust", "cargo test", f"{relative_manifest} (standard candidate; inspect build scripts and CI first)"))
            candidates.append(_candidate("Rust", "cargo build", f"{relative_manifest} (standard candidate; inspect build scripts and CI first)"))
            if "[lints" in cargo_lower or "clippy" in cargo_lower:
                candidates.append(_candidate("Rust", "cargo clippy --all-targets --all-features", f"{relative_manifest} (lint candidate; confirm project configuration)"))
            candidates.append(_candidate("Rust", "cargo fmt --all -- --check", f"{relative_manifest} (format candidate; read-only check)"))
        elif relative_manifest == "Makefile" or relative_manifest.endswith("/Makefile"):
            makefile = _safe_read(root, relative_manifest)
            if makefile is None:
                warnings.append(f"{relative_manifest} could not be read safely; ignored.")
                continue
            recipes: dict[str, str] = {}
            current: Optional[str] = None
            for line in makefile.splitlines():
                target = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?![=])", line)
                if target:
                    current = target.group(1)
                    recipes.setdefault(current, "")
                elif current and line.startswith("\t"):
                    recipes[current] += " " + line.strip()
                elif line and not line[0].isspace():
                    current = None
            for name in sorted(set(recipes) & CHECK_NAMES):
                candidates.append(_candidate("Make", f"make {name}", f"{relative_manifest}:{name}", _risk_flags(name, recipes[name])))

    workflow_dir = root / ".github" / "workflows"
    workflows: list[str] = []
    if workflow_dir.is_dir():
        try:
            if not workflow_dir.resolve(strict=True).is_relative_to(root):
                warnings.append("GitHub workflow directory resolves outside the repository; ignored.")
            else:
                workflows = sorted(
                    str(path.relative_to(root)).replace("\\", "/")
                    for path in workflow_dir.iterdir()
                    if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
                    and path.resolve().is_relative_to(root)
                )
        except (OSError, RuntimeError):
            warnings.append("GitHub workflow directory could not be safely inspected.")

    return {
        "manifests_found": manifests,
        "workflow_files": workflows,
        "verification_candidates": candidates,
        "warnings": warnings,
        "execution_policy": "Candidates only; no project command was executed.",
    }


def _split_paths(raw: str) -> list[str]:
    return [part for part in raw.split("\0") if part]


def _check_untracked_whitespace(root: Path, paths: list[str]) -> dict[str, Any]:
    if not paths:
        return {"name": "untracked_file_whitespace", "status": "SKIPPED", "reason": "No untracked files were present."}
    findings: list[str] = []
    unknown: list[str] = []
    for relative in paths:
        path = root / relative
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.stat().st_size > 5_000_000:
                unknown.append(relative)
                continue
            data = resolved.read_bytes()
        except (OSError, RuntimeError):
            unknown.append(relative)
            continue
        if b"\0" in data:
            unknown.append(relative)
            continue
        for number, line in enumerate(data.splitlines(), 1):
            if line.endswith((b" ", b"\t")):
                findings.append(f"{relative}:{number}")
    if findings:
        return {"name": "untracked_file_whitespace", "status": "FAIL", "findings": findings[:100]}
    if unknown:
        return {"name": "untracked_file_whitespace", "status": "UNKNOWN", "reason": "Some untracked files were binary, too large, unreadable, or outside the repository.", "paths": unknown[:100]}
    return {"name": "untracked_file_whitespace", "status": "PASS", "files_checked": len(paths)}


def inspect_repository(repo: Path, base: Optional[str] = None) -> dict[str, Any]:
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory.")

    top = _run_git(repo, ["rev-parse", "--show-toplevel"])
    if not top.get("started") or top.get("returncode") != 0:
        return {
            "tool": "DiffProof",
            "version": VERSION,
            "repository_status": "UNKNOWN",
            "reason": top.get("error") or top.get("stderr", "Path is not a Git repository.").strip() or "Git repository not detected.",
            "changes_detected": None,
            **discover_candidates(repo),
        }
    root = Path(top["stdout"].strip()).resolve()
    if not root.is_dir():
        raise ValueError("Git returned an invalid repository root.")

    head_result = _run_git(root, ["rev-parse", "--verify", "HEAD"])
    head = head_result.get("stdout", "").strip() if head_result.get("returncode") == 0 else None
    status = _run_git(root, ["status", "--porcelain=v1", "--untracked-files=all"])
    if status.get("returncode") != 0:
        return {"tool": "DiffProof", "version": VERSION, "repository_status": "UNKNOWN", "reason": "Git status could not be read.", "changes_detected": None, **discover_candidates(root)}
    status_lines = [line for line in status.get("stdout", "").splitlines() if line]

    changes: dict[str, list[str]] = {"working_tree": [], "staged": [], "untracked": [], "base_to_head": []}
    base_comparison_status = "NOT RUN" if base is None else "UNKNOWN"
    path_inventory_status = "PASS"
    for key, args in (
        ("working_tree", ["diff", "--name-only", "--no-renames", "-z"]),
        ("staged", ["diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD"] if head else ["diff", "--cached", "--name-only", "--no-renames", "-z"]),
        ("untracked", ["ls-files", "--others", "--exclude-standard", "-z"]),
    ):
        result = _run_git(root, args)
        if result.get("returncode") == 0:
            changes[key] = _split_paths(result.get("stdout", ""))
        else:
            path_inventory_status = "UNKNOWN"
            changes[f"{key}_error"] = ["Git path inventory command failed; inspect the worktree manually."]
    if head:
        if base:
            resolved = _run_git(root, ["rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"])
            if resolved.get("returncode") == 0:
                base_sha = resolved["stdout"].strip()
                result = _run_git(root, ["diff", "--name-only", "--no-renames", "-z", f"{base_sha}...HEAD"])
                if result.get("returncode") == 0:
                    changes["base_to_head"] = _split_paths(result.get("stdout", ""))
                    base_comparison_status = "PASS"
                else:
                    changes["base_to_head_error"] = ["Base comparison failed; inspect the diff manually."]
            else:
                changes["base_to_head_error"] = ["Requested base did not resolve to a commit; no base comparison was made."]

    checks: list[dict[str, Any]] = []
    for label, args in (
        ("working_diff_whitespace", ["diff", "--check", "--no-ext-diff", "--no-textconv"]),
        ("staged_diff_whitespace", ["diff", "--cached", "--check", "--no-ext-diff", "--no-textconv"]),
    ):
        result = _run_git(root, args)
        if not result.get("started") or result.get("timeout") or result.get("returncode") is None:
            check = {"name": label, "status": "UNKNOWN", "reason": result.get("error", "Git check did not return an exit status.")}
        else:
            check = {"name": label, "status": "PASS" if result["returncode"] == 0 else "FAIL", "command": "git diff --check", "exit_code": result["returncode"]}
            detail = (result.get("stdout", "") + result.get("stderr", "")).strip()
            if detail:
                check["output_excerpt"] = detail[:2000]
        checks.append(check)
    checks.append(_check_untracked_whitespace(root, changes["untracked"]))

    local_changes = bool(status_lines)
    if base is None:
        changes_detected = local_changes
        change_summary = (
            "CHANGES DETECTED; PATH INVENTORY UNKNOWN"
            if local_changes and path_inventory_status == "UNKNOWN"
            else "CHANGES DETECTED" if local_changes
            else "NO WORKTREE CHANGES; BASE NOT COMPARED"
        )
    elif base_comparison_status == "PASS":
        changes_detected = local_changes or bool(changes["base_to_head"])
        change_summary = (
            "CHANGES DETECTED; PATH INVENTORY UNKNOWN"
            if changes_detected and path_inventory_status == "UNKNOWN"
            else "CHANGES DETECTED" if changes_detected
            else "NO CHANGE DETECTED"
        )
    else:
        changes_detected = True if local_changes else None
        change_summary = (
            "CHANGES DETECTED; BASE COMPARISON UNKNOWN"
            if local_changes
            else "UNKNOWN — BASE COMPARISON FAILED"
        )
    repo_inventory = discover_candidates(root)
    return {
        "tool": "DiffProof",
        "version": VERSION,
        "repository_status": "AVAILABLE",
        "repository_root": str(root),
        "head": head,
        "base_requested": base,
        "base_comparison_status": base_comparison_status,
        "path_inventory_status": path_inventory_status,
        "changes_detected": changes_detected,
        "change_summary": change_summary,
        "git_status_porcelain": status_lines,
        "changed_paths": changes,
        "executed_inspection_checks": checks,
        **repo_inventory,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect Git state and likely verification commands without running project checks.")
    subparsers = parser.add_subparsers(dest="action", required=True)
    inspect = subparsers.add_parser("inspect", help="Produce a read-only repository inventory as JSON.")
    inspect.add_argument("--repo", default=".", help="Repository directory (default: current directory).")
    inspect.add_argument("--base", help="Optional commit or ref to compare with HEAD; no fetch is performed.")
    args = parser.parse_args(argv)
    try:
        result = inspect_repository(Path(args.repo), args.base)
    except ValueError as exc:
        print(json.dumps({"tool": "DiffProof", "version": VERSION, "repository_status": "UNKNOWN", "reason": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("repository_status") == "UNKNOWN":
        return 2
    if any(item.get("status") == "FAIL" for item in result.get("executed_inspection_checks", [])):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
