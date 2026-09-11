from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import fork_refresh_acceptance as refresh


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout.strip()


def _write_commit(repo: Path, path: str, content: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _fixture(tmp_path: Path) -> tuple[Path, dict]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "rerere.enabled", "true")
    _git(repo, "config", "rerere.autoupdate", "false")
    frozen = _write_commit(repo, "base.txt", "base\n", "frozen")

    _git(repo, "switch", "-c", "candidate/topic-a")
    candidate = _write_commit(repo, "topic.txt", "topic\n", "topic")
    _git(repo, "branch", "candidate/integration", candidate)

    _git(repo, "switch", "-c", "closure", frozen)
    closure = _write_commit(repo, "upstream.txt", "upstream\n", "closure")

    manifest = {
        "schema_version": 1,
        "frozen_upstream_sha": frozen,
        "closure_upstream_sha": closure,
        "integration_candidate_ref": "candidate/integration",
        "candidate_head_sha": candidate,
        "rollback_ref": "backup/fixture/pre-compose",
        "rerere": {"enabled": True, "autoupdate": False},
        "topics": [
            {
                "name": "topic-a",
                "ref": "candidate/topic-a",
                "dependencies": [],
                "owned_paths": ["topic.txt"],
                "focused_gates": [[sys.executable, "-c", "print('focused pass')"]],
            }
        ],
        "composition_order": ["topic-a"],
        "import_origin_checks": [[sys.executable, "-c", "print('origin pass')"]],
        "canonical_gates": [[sys.executable, "-c", "print('canonical pass')"]],
        "closure_artifacts": {
            "report": ".fork-refresh/closure.json",
            "log_dir": ".fork-refresh/logs",
        },
    }
    return repo, manifest


def _manifest_file(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_valid_manifest_and_repository(tmp_path):
    repo, manifest = _fixture(tmp_path)
    loaded = refresh.load_manifest(_manifest_file(tmp_path, manifest))
    assert refresh.validate_repository(repo, loaded, require_clean=True)["candidate"] == manifest["candidate_head_sha"]


def test_malformed_manifest_is_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(refresh.RefreshError, match="malformed manifest"):
        refresh.load_manifest(path)


def test_missing_ref_is_rejected(tmp_path):
    repo, manifest = _fixture(tmp_path)
    manifest["topics"][0]["ref"] = "candidate/missing"
    with pytest.raises(refresh.RefreshError, match="command failed"):
        refresh.validate_repository(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)), require_clean=True)


def test_stale_candidate_identity_is_rejected(tmp_path):
    repo, manifest = _fixture(tmp_path)
    manifest["candidate_head_sha"] = manifest["frozen_upstream_sha"]
    with pytest.raises(refresh.RefreshError, match="stale manifest"):
        refresh.validate_repository(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)), require_clean=True)


def test_ancestry_mismatch_is_rejected(tmp_path):
    repo, manifest = _fixture(tmp_path)
    _git(repo, "switch", "--orphan", "unrelated")
    _git(repo, "rm", "-rf", "--ignore-unmatch", "--", ".")
    unrelated = _write_commit(repo, "other.txt", "other\n", "unrelated")
    manifest["closure_upstream_sha"] = unrelated
    with pytest.raises(refresh.RefreshError, match="not descended"):
        refresh.validate_repository(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)), require_clean=True)


def test_dirty_state_is_rejected(tmp_path):
    repo, manifest = _fixture(tmp_path)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(refresh.RefreshError, match="dirty worktree"):
        refresh.validate_repository(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)), require_clean=True)


def test_topic_dependency_ordering_is_rejected(tmp_path):
    _repo, manifest = _fixture(tmp_path)
    manifest["topics"].append(
        {
            "name": "topic-b",
            "ref": "candidate/topic-a",
            "dependencies": ["topic-a"],
            "owned_paths": ["topic.txt"],
            "focused_gates": [[sys.executable, "-c", "print('topic b pass')"]],
        }
    )
    manifest["composition_order"] = ["topic-b", "topic-a"]
    with pytest.raises(refresh.RefreshError, match="dependency ordering"):
        refresh.load_manifest(_manifest_file(tmp_path, manifest))


def test_missing_required_tests_are_rejected(tmp_path):
    _repo, manifest = _fixture(tmp_path)
    manifest["topics"][0]["focused_gates"] = []
    with pytest.raises(refresh.RefreshError, match="missing focused tests"):
        refresh.load_manifest(_manifest_file(tmp_path, manifest))


def test_independent_topic_overlap_is_rejected(tmp_path):
    repo, manifest = _fixture(tmp_path)
    _git(repo, "switch", "-c", "candidate/topic-b", manifest["frozen_upstream_sha"])
    _write_commit(repo, "topic.txt", "competing topic\n", "topic b")
    _git(repo, "switch", "closure")
    manifest["topics"].append(
        {
            "name": "topic-b",
            "ref": "candidate/topic-b",
            "dependencies": [],
            "owned_paths": ["topic.txt"],
            "focused_gates": [[sys.executable, "-c", "print('topic b pass')"]],
        }
    )
    manifest["composition_order"].append("topic-b")
    with pytest.raises(refresh.RefreshError, match="unresolved topic overlap"):
        refresh.validate_repository(
            repo,
            refresh.load_manifest(_manifest_file(tmp_path, manifest)),
            require_clean=True,
        )


def test_no_overlap_fast_path_runs_no_model_command_and_writes_artifacts(tmp_path, monkeypatch):
    repo, manifest = _fixture(tmp_path)
    marker = tmp_path / "model-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    model = fake_bin / "model"
    model.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    model.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    result = refresh.certify(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)))

    assert result["model_calls"] == 0
    assert not marker.exists()
    report = json.loads((repo / ".fork-refresh/closure.json").read_text(encoding="utf-8"))
    assert report["mode"] == "certified-zero-model-no-semantic-overlap"
    assert len(report["gates"]) == 3


def test_changed_path_overlap_requires_human_review(tmp_path):
    repo, manifest = _fixture(tmp_path)
    _git(repo, "switch", "closure")
    manifest["closure_upstream_sha"] = _write_commit(repo, "topic.txt", "upstream collision\n", "overlap")
    with pytest.raises(refresh.RefreshError, match="changed-path overlap"):
        refresh.certify(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)))


def test_same_symbol_overlap_across_paths_requires_human_review(tmp_path):
    repo, manifest = _fixture(tmp_path)
    _git(repo, "switch", "candidate/topic-a")
    candidate = _write_commit(repo, "candidate.py", "def shared_symbol():\n    return 1\n", "candidate symbol")
    _git(repo, "branch", "-f", "candidate/integration", candidate)
    manifest["candidate_head_sha"] = candidate
    manifest["topics"][0]["owned_paths"].append("candidate.py")
    _git(repo, "switch", "closure")
    closure = _write_commit(repo, "upstream.py", "def shared_symbol():\n    return 2\n", "upstream symbol")
    manifest["closure_upstream_sha"] = closure
    with pytest.raises(refresh.RefreshError, match="changed-symbol overlap"):
        refresh.certify(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)))


def test_unresolved_marker_is_rejected(tmp_path):
    repo, manifest = _fixture(tmp_path)
    _git(repo, "switch", "candidate/topic-a")
    candidate = _write_commit(repo, "marker.txt", "<<<<<<< ours\n=======\n>>>>>>> theirs\n", "marker")
    _git(repo, "branch", "-f", "candidate/integration", candidate)
    manifest["candidate_head_sha"] = candidate
    manifest["topics"][0]["owned_paths"].append("marker.txt")
    _git(repo, "switch", "closure")
    with pytest.raises(refresh.RefreshError, match="conflict marker"):
        refresh.certify(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)))


def test_failed_focused_gate_is_rejected_with_log(tmp_path):
    repo, manifest = _fixture(tmp_path)
    manifest["topics"][0]["focused_gates"] = [[sys.executable, "-c", "raise SystemExit(7)"]]
    with pytest.raises(refresh.RefreshError, match="acceptance gate failed"):
        refresh.certify(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)))
    logs = list((repo / ".fork-refresh/logs").glob("*.log"))
    assert len(logs) == 1


def test_contaminated_import_origin_gate_is_rejected(tmp_path):
    repo, manifest = _fixture(tmp_path)
    manifest["import_origin_checks"] = [[sys.executable, "-c", "raise SystemExit('foreign import')"]]
    with pytest.raises(refresh.RefreshError, match="acceptance gate failed"):
        refresh.certify(repo, refresh.load_manifest(_manifest_file(tmp_path, manifest)))


def test_disposable_composition_creates_rollback_and_rebases_candidate(tmp_path):
    repo, manifest = _fixture(tmp_path)
    result = refresh.compose(
        repo,
        refresh.load_manifest(_manifest_file(tmp_path, manifest)),
        disposable_candidate=True,
    )

    assert _git(repo, "rev-parse", "backup/fixture/pre-compose") == manifest["candidate_head_sha"]
    assert _git(repo, "rev-parse", "candidate/integration") == result["candidate_sha"]
    assert refresh._ancestor(repo, manifest["closure_upstream_sha"], result["candidate_sha"])
    assert result["model_calls"] == 0


def test_composition_requires_explicit_disposable_mode(tmp_path):
    repo, manifest = _fixture(tmp_path)
    with pytest.raises(refresh.RefreshError, match="requires --disposable-candidate"):
        refresh.compose(
            repo,
            refresh.load_manifest(_manifest_file(tmp_path, manifest)),
            disposable_candidate=False,
        )
