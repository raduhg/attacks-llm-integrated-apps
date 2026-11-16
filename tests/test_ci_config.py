"""The CI workflow is security-relevant configuration, so its key properties are tested:
every third-party action pinned to a commit SHA, and a read-only workflow token."""

from __future__ import annotations

import re

import yaml

from testbed.config import PROJECT_ROOT

WORKFLOWS = sorted((PROJECT_ROOT / ".github" / "workflows").glob("*.yml"))


def test_every_action_is_pinned_to_a_commit_sha() -> None:
    assert WORKFLOWS
    for path in WORKFLOWS:
        uses = re.findall(r"uses:\s*(\S+)", path.read_text(encoding="utf-8"))
        assert uses, path
        for ref in uses:
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{path.name}: {ref} is not pinned to a SHA"


def test_workflow_token_is_read_only_and_no_secrets_are_used() -> None:
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        workflow = yaml.safe_load(text)
        assert workflow["permissions"] == {"contents": "read"}, path.name
        assert all("permissions" not in job for job in workflow["jobs"].values()), "no job may widen the token"
        assert set(re.findall(r"secrets\.(\w+)", text)) <= {"GITHUB_TOKEN"}, "CI must not use the API key"


def test_ci_runs_on_pull_requests_with_the_four_required_jobs() -> None:
    workflow = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    triggers = workflow[True]  # YAML parses the key `on` as the boolean True
    assert "pull_request" in triggers
    assert set(workflow["jobs"]) == {"lint", "test", "security", "build"}
