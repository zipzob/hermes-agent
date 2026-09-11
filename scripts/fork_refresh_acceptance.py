#!/usr/bin/env python3
"""Manifest-driven native-Git fork refresh and acceptance.

The certified fast path is deliberately model-free and fail-closed. It only
composes refs in a caller-declared disposable candidate repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Sequence


_SHA = re.compile(r"^[0-9a-f]{40}$")
_REF = re.compile(r"^(candidate|backup)/[A-Za-z0-9._/-]+$")
_CONFLICT_MARKER = re.compile(r"^(<<<<<<< |=======\s*$|>>>>>>> )", re.MULTILINE)
_SYMBOL = re.compile(
    r"^[+-]\s*(?:async\s+)?(?:def|class|function|interface|type|enum|struct|fn)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_REQUIRED_KEYS = {
    "schema_version",
    "frozen_upstream_sha",
    "closure_upstream_sha",
    "integration_candidate_ref",
    "candidate_head_sha",
    "rollback_ref",
    "rerere",
    "topics",
    "composition_order",
    "import_origin_checks",
    "canonical_gates",
    "closure_artifacts",
}
_TOPIC_KEYS = {"name", "ref", "dependencies", "owned_paths", "focused_gates"}


class RefreshError(RuntimeError):
    """A deterministic refresh precondition or acceptance gate failed."""


def _run(
    argv: Sequence[str], *, cwd: Path, check: bool = True, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv), cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, env=env,
    )
    if check and result.returncode:
        raise RefreshError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stdout}"
        )
    return result


def _git(repo: Path, *args: str, check: bool = True) -> str:
    return _run(("git", *args), cwd=repo, check=check).stdout.strip()


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise RefreshError(f"{label} must be a non-empty repository-relative path")
    return value


def _command(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise RefreshError(f"{label} must be a non-empty argv array")
    return list(value)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RefreshError(f"malformed manifest: {exc}") from exc
    if not isinstance(data, dict) or set(data) != _REQUIRED_KEYS:
        raise RefreshError("manifest keys do not match the version-1 contract")
    if data["schema_version"] != 1:
        raise RefreshError("unsupported manifest schema_version")
    for key in ("frozen_upstream_sha", "closure_upstream_sha", "candidate_head_sha"):
        if not isinstance(data[key], str) or not _SHA.fullmatch(data[key]):
            raise RefreshError(f"{key} must be a lowercase 40-character Git SHA")
    for key in ("integration_candidate_ref", "rollback_ref"):
        if not isinstance(data[key], str) or not _REF.fullmatch(data[key]):
            raise RefreshError(f"{key} must stay under candidate/ or backup/")
    rerere = data["rerere"]
    if rerere != {"enabled": True, "autoupdate": False}:
        raise RefreshError("manifest must require rerere.enabled=true and rerere.autoupdate=false")
    topics = data["topics"]
    if not isinstance(topics, list) or not topics:
        raise RefreshError("topics must be a non-empty list")
    names: set[str] = set()
    for index, topic in enumerate(topics):
        if not isinstance(topic, dict) or set(topic) != _TOPIC_KEYS:
            raise RefreshError(f"topics[{index}] keys do not match the contract")
        name = topic["name"]
        if not isinstance(name, str) or not name or name in names:
            raise RefreshError("topic names must be unique non-empty strings")
        names.add(name)
        if not isinstance(topic["ref"], str) or not _REF.fullmatch(topic["ref"]):
            raise RefreshError(f"topic {name} ref must stay under candidate/ or backup/")
        if not isinstance(topic["dependencies"], list) or not all(
            isinstance(dep, str) for dep in topic["dependencies"]
        ):
            raise RefreshError(f"topic {name} dependencies must be a string list")
        if not isinstance(topic["owned_paths"], list) or not topic["owned_paths"]:
            raise RefreshError(f"topic {name} must declare owned_paths")
        topic["owned_paths"] = [
            _relative_path(value, f"topic {name} owned path") for value in topic["owned_paths"]
        ]
        topic["focused_gates"] = [
            _command(value, f"topic {name} focused gate") for value in topic["focused_gates"]
        ]
        if not topic["focused_gates"]:
            raise RefreshError(f"topic {name} is missing focused tests")
    order = data["composition_order"]
    if not isinstance(order, list) or set(order) != names or len(order) != len(names):
        raise RefreshError("composition_order must contain every topic exactly once")
    position = {name: index for index, name in enumerate(order)}
    for topic in topics:
        for dependency in topic["dependencies"]:
            if dependency not in names or position[dependency] >= position[topic["name"]]:
                raise RefreshError(f"topic dependency ordering is invalid for {topic['name']}")
    data["import_origin_checks"] = [
        _command(value, "import origin check") for value in data["import_origin_checks"]
    ]
    data["canonical_gates"] = [
        _command(value, "canonical gate") for value in data["canonical_gates"]
    ]
    if not data["import_origin_checks"] or not data["canonical_gates"]:
        raise RefreshError("import-origin checks and canonical gates must not be empty")
    artifacts = data["closure_artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != {"report", "log_dir"}:
        raise RefreshError("closure_artifacts must contain report and log_dir")
    artifacts["report"] = _relative_path(artifacts["report"], "closure report")
    artifacts["log_dir"] = _relative_path(artifacts["log_dir"], "closure log_dir")
    return data


def _verify_repo(repo: Path) -> None:
    root = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    if root != repo.resolve():
        raise RefreshError(f"--repo must be the Git root: {root}")
    if _git(repo, "rev-parse", "--is-shallow-repository") != "false":
        raise RefreshError("shallow repositories are not accepted")


def _verify_ref(repo: Path, ref: str) -> str:
    value = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not _SHA.fullmatch(value):
        raise RefreshError(f"ref did not resolve to a commit: {ref}")
    return value


def _ancestor(repo: Path, parent: str, child: str) -> bool:
    return _run(("git", "merge-base", "--is-ancestor", parent, child), cwd=repo, check=False).returncode == 0


def _changed_paths(repo: Path, old: str, new: str) -> set[str]:
    output = _git(repo, "diff", "--name-only", "--no-renames", old, new)
    return {line for line in output.splitlines() if line}


def _changed_symbols(repo: Path, old: str, new: str) -> set[str]:
    patch = _git(repo, "diff", "--unified=0", "--no-renames", old, new)
    return set(_SYMBOL.findall(patch))


def _verify_clean(repo: Path) -> None:
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RefreshError("dirty worktree rejected")


def validate_repository(repo: Path, manifest: dict[str, Any], *, require_clean: bool) -> dict[str, Any]:
    _verify_repo(repo)
    if require_clean:
        _verify_clean(repo)
    if _git(repo, "config", "--bool", "rerere.enabled") != "true":
        raise RefreshError("rerere.enabled must be true")
    if _git(repo, "config", "--bool", "rerere.autoupdate") != "false":
        raise RefreshError("rerere.autoupdate must be false")
    frozen = _verify_ref(repo, manifest["frozen_upstream_sha"])
    closure = _verify_ref(repo, manifest["closure_upstream_sha"])
    candidate = _verify_ref(repo, manifest["integration_candidate_ref"])
    if candidate != manifest["candidate_head_sha"]:
        raise RefreshError("stale manifest: candidate_head_sha does not match candidate ref")
    if not _ancestor(repo, frozen, closure):
        raise RefreshError("closure upstream is not descended from frozen upstream")
    if not _ancestor(repo, frozen, candidate):
        raise RefreshError("candidate is not descended from frozen upstream")
    topics = {topic["name"]: topic for topic in manifest["topics"]}
    for topic in manifest["topics"]:
        tip = _verify_ref(repo, topic["ref"])
        parent = frozen
        for dependency in topic["dependencies"]:
            dependency_tip = _verify_ref(repo, topics[dependency]["ref"])
            if not _ancestor(repo, dependency_tip, tip):
                raise RefreshError(f"topic {topic['name']} does not descend from {dependency}")
            parent = dependency_tip
        if not _ancestor(repo, parent, tip):
            raise RefreshError(f"invalid ancestry for topic {topic['name']}")
        actual = _changed_paths(repo, parent, tip)
        declared = set(topic["owned_paths"])
        if not actual or not actual <= declared:
            raise RefreshError(f"topic ownership is stale or incomplete for {topic['name']}")
    for index, left in enumerate(manifest["topics"]):
        left_tip = _verify_ref(repo, left["ref"])
        left_parent = (
            _verify_ref(repo, topics[left["dependencies"][-1]]["ref"])
            if left["dependencies"] else frozen
        )
        for right in manifest["topics"][index + 1:]:
            if left["name"] in right["dependencies"] or right["name"] in left["dependencies"]:
                continue
            right_tip = _verify_ref(repo, right["ref"])
            right_parent = (
                _verify_ref(repo, topics[right["dependencies"][-1]]["ref"])
                if right["dependencies"] else frozen
            )
            paths = sorted(
                _changed_paths(repo, left_parent, left_tip)
                & _changed_paths(repo, right_parent, right_tip)
            )
            symbols = sorted(
                _changed_symbols(repo, left_parent, left_tip)
                & _changed_symbols(repo, right_parent, right_tip)
            )
            if paths or symbols:
                raise RefreshError(
                    f"unresolved topic overlap between {left['name']} and {right['name']}: "
                    f"paths={paths}, symbols={symbols}"
                )
    if _git(repo, "ls-files", "-u"):
        raise RefreshError("unmerged index entries remain")
    if _git(repo, "rerere", "remaining"):
        raise RefreshError("rerere reports unresolved paths")
    return {"frozen": frozen, "closure": closure, "candidate": candidate}


def _prove_no_overlap(repo: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    frozen = manifest["frozen_upstream_sha"]
    closure = manifest["closure_upstream_sha"]
    candidate = manifest["candidate_head_sha"]
    upstream_paths = _changed_paths(repo, frozen, closure)
    candidate_paths = _changed_paths(repo, frozen, candidate)
    path_overlap = sorted(upstream_paths & candidate_paths)
    if path_overlap:
        raise RefreshError(f"human review required: changed-path overlap: {path_overlap}")
    upstream_symbols = _changed_symbols(repo, frozen, closure)
    candidate_symbols = _changed_symbols(repo, frozen, candidate)
    symbol_overlap = sorted(upstream_symbols & candidate_symbols)
    if symbol_overlap:
        raise RefreshError(f"human review required: changed-symbol overlap: {symbol_overlap}")
    name_status = _git(repo, "diff", "--name-status", "-M", frozen, closure)
    owned = {path for topic in manifest["topics"] for path in topic["owned_paths"]}
    moved = []
    for line in name_status.splitlines():
        fields = line.split("\t")
        if fields and fields[0].startswith("R") and any(path in owned for path in fields[1:]):
            moved.append(fields[1:])
    if moved:
        raise RefreshError(f"human review required: moved topic ownership: {moved}")
    return {
        "upstream_paths": sorted(upstream_paths),
        "candidate_paths": sorted(candidate_paths),
        "path_overlap": [],
        "symbol_overlap": [],
    }


def _scan_markers(repo: Path, ref: str | None = None) -> None:
    tree = ref or "HEAD"
    result = _run(
        (
            "git", "grep", "-n", "-I", "-E",
            r"^(<<<<<<< |=======$|>>>>>>> )", tree, "--",
        ),
        cwd=repo,
        check=False,
    )
    if result.returncode == 0:
        raise RefreshError(f"unresolved conflict marker: {result.stdout.strip()}")
    if result.returncode != 1:
        raise RefreshError(f"conflict-marker scan failed: {result.stdout.strip()}")


def _run_gates(repo: Path, manifest: dict[str, Any], log_dir: Path) -> list[dict[str, Any]]:
    gates: list[tuple[str, list[str]]] = []
    topics = {topic["name"]: topic for topic in manifest["topics"]}
    for name in manifest["composition_order"]:
        gates.extend((f"focused:{name}", gate) for gate in topics[name]["focused_gates"])
    gates.extend(("import-origin", gate) for gate in manifest["import_origin_checks"])
    gates.extend(("canonical", gate) for gate in manifest["canonical_gates"])
    log_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, (kind, argv) in enumerate(gates, 1):
        result = _run(argv, cwd=repo, check=False, env={**os.environ, "FORK_REFRESH_MODEL_CALLS": "forbidden"})
        log = log_dir / f"{index:03d}-{kind.replace(':', '-')}.log"
        log.write_text(result.stdout, encoding="utf-8")
        row = {"kind": kind, "argv": argv, "exit_code": result.returncode, "log": str(log)}
        results.append(row)
        if result.returncode:
            raise RefreshError(f"acceptance gate failed: {' '.join(argv)} (log: {log})")
    return results


def certify(repo: Path, manifest: dict[str, Any], *, require_clean: bool = True) -> dict[str, Any]:
    identity = validate_repository(repo, manifest, require_clean=require_clean)
    overlap = _prove_no_overlap(repo, manifest)
    _scan_markers(repo, manifest["candidate_head_sha"])
    artifacts = manifest["closure_artifacts"]
    gates = _run_gates(repo, manifest, repo / artifacts["log_dir"])
    report = {
        "schema_version": 1,
        "mode": "certified-zero-model-no-semantic-overlap",
        "model_calls": 0,
        "identity": identity,
        "overlap": overlap,
        "gates": gates,
        "rerere": {"enabled": True, "autoupdate": False, "remaining": []},
    }
    report_path = repo / artifacts["report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def compose(repo: Path, manifest: dict[str, Any], *, disposable_candidate: bool) -> dict[str, Any]:
    if not disposable_candidate:
        raise RefreshError("composition requires --disposable-candidate")
    identity = validate_repository(repo, manifest, require_clean=True)
    _prove_no_overlap(repo, manifest)
    candidate_ref = manifest["integration_candidate_ref"]
    rollback_ref = manifest["rollback_ref"]
    if _run(("git", "show-ref", "--verify", "--quiet", f"refs/heads/{rollback_ref}"), cwd=repo, check=False).returncode == 0:
        raise RefreshError("rollback ref already exists; refusing ambiguous reuse")
    _git(repo, "update-ref", f"refs/heads/{rollback_ref}", identity["candidate"])
    temp_root = Path(tempfile.mkdtemp(prefix="fork-refresh-compose-"))
    worktree = temp_root / "worktree"
    try:
        _git(repo, "worktree", "add", "--detach", str(worktree), identity["candidate"])
        _git(
            worktree, "rebase", "--onto", identity["closure"], identity["frozen"],
            check=True,
        )
        _scan_markers(worktree)
        gates = _run_gates(
            worktree, manifest,
            repo / manifest["closure_artifacts"]["log_dir"],
        )
        composed = _git(worktree, "rev-parse", "HEAD")
        _git(
            repo, "update-ref", f"refs/heads/{candidate_ref}", composed,
            identity["candidate"],
        )
        return {
            "rollback_ref": rollback_ref,
            "rollback_sha": identity["candidate"],
            "candidate_ref": candidate_ref,
            "candidate_sha": composed,
            "model_calls": 0,
            "gates": gates,
        }
    finally:
        _run(("git", "worktree", "remove", "--force", str(worktree)), cwd=repo, check=False)
        shutil.rmtree(temp_root, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "certify", "compose"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--allow-dirty-snapshot", action="store_true")
    parser.add_argument("--disposable-candidate", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.action == "validate":
            result = validate_repository(
                args.repo, manifest, require_clean=not args.allow_dirty_snapshot
            )
        elif args.action == "certify":
            result = certify(
                args.repo, manifest, require_clean=not args.allow_dirty_snapshot
            )
        else:
            if args.allow_dirty_snapshot:
                raise RefreshError("composition never accepts dirty state")
            result = compose(
                args.repo, manifest, disposable_candidate=args.disposable_candidate
            )
    except RefreshError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
