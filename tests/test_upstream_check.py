from __future__ import annotations

import base64
from pathlib import Path

import pytest

from scripts.check_upstream_update import (
    Candidate,
    existing_issue_url,
    get_build_number,
    is_stable_tag,
    issue_title,
    read_pinned_commit,
    render_issue_body,
    select_candidate,
    should_open_update,
)


class FakeClient:
    def __init__(self, responses: dict[tuple[str, str], object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, object | None]] = []

    def request_json(self, method: str, path: str, payload: object | None = None) -> object:
        self.calls.append((method, path, payload))
        return self.responses[(method, path)]


def test_read_pinned_commit(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.11-slim\n"
        "ARG NCA_UPSTREAM_COMMIT=0123456789abcdef0123456789abcdef01234567\n"
    )

    assert read_pinned_commit(dockerfile) == "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    ("tag", "stable"),
    [
        ("v1.2.3", True),
        ("build-220", True),
        ("v1.2.3-rc1", False),
        ("v1.2.3-beta.2", False),
        ("nightly-2026-08-01", False),
        ("v2-preview", False),
    ],
)
def test_is_stable_tag(tag: str, stable: bool) -> None:
    assert is_stable_tag(tag) is stable


def test_select_candidate_prefers_latest_stable_release() -> None:
    repo = "example/nca"
    client = FakeClient(
        {
            ("GET", f"/repos/{repo}/releases?per_page=100"): [
                {
                    "tag_name": "v2.0.0-rc1",
                    "draft": False,
                    "prerelease": True,
                    "published_at": "2026-08-10T00:00:00Z",
                    "created_at": "2026-08-10T00:00:00Z",
                    "html_url": "https://example.invalid/rc",
                },
                {
                    "tag_name": "v1.9.0",
                    "draft": False,
                    "prerelease": False,
                    "published_at": "2026-08-01T00:00:00Z",
                    "created_at": "2026-08-01T00:00:00Z",
                    "html_url": "https://example.invalid/stable",
                },
            ],
            ("GET", f"/repos/{repo}/commits/v1.9.0"): {"sha": "a" * 40},
        }
    )

    candidate = select_candidate(client, repo)

    assert candidate.kind == "release"
    assert candidate.ref == "v1.9.0"
    assert candidate.sha == "a" * 40
    assert not any("tags?" in path for _, path, _ in client.calls)


def test_select_candidate_falls_back_to_default_branch() -> None:
    repo = "example/nca"
    client = FakeClient(
        {
            ("GET", f"/repos/{repo}/releases?per_page=100"): [],
            ("GET", f"/repos/{repo}/tags?per_page=100"): [],
            ("GET", f"/repos/{repo}/"): {"default_branch": "main"},
            ("GET", f"/repos/{repo}/commits/main"): {
                "sha": "b" * 40,
                "html_url": "https://example.invalid/commit",
                "commit": {
                    "committer": {"date": "2026-08-01T00:00:00Z"},
                    "author": {"date": "2026-08-01T00:00:00Z"},
                },
            },
        }
    )

    candidate = select_candidate(client, repo)

    assert candidate.kind == "default-branch"
    assert candidate.ref == "main"
    assert candidate.sha == "b" * 40
    assert "no stable release or tag" in candidate.label


def test_get_build_number_decodes_github_content() -> None:
    repo = "example/nca"
    sha = "c" * 40
    encoded = base64.b64encode(b"220\n").decode()
    client = FakeClient(
        {
            ("GET", f"/repos/{repo}/contents/build_number.txt?ref={sha}"): {
                "encoding": "base64",
                "content": encoded,
            }
        }
    )

    assert get_build_number(client, repo, sha) == "220"


def test_should_open_update_handles_relationships() -> None:
    pinned = "a" * 40
    candidate = "b" * 40

    assert not should_open_update(pinned, pinned, None)
    assert not should_open_update(pinned, candidate, {"status": "behind"})
    assert not should_open_update(pinned, candidate, {"status": "identical"})
    assert should_open_update(pinned, candidate, {"status": "ahead"})
    assert should_open_update(pinned, candidate, {"status": "diverged"})
    assert should_open_update(pinned, candidate, None)


def test_existing_issue_url_makes_update_notifications_idempotent() -> None:
    repo = "hallcyn/no-code-architects-toolkit"
    sha = "d" * 40
    marker = f"<!-- nca-upstream-sha: {sha} -->"
    client = FakeClient(
        {
            ("GET", f"/repos/{repo}/issues?state=all&per_page=100&page=1"): [
                {
                    "body": marker,
                    "html_url": "https://example.invalid/issues/42",
                }
            ]
        }
    )

    assert existing_issue_url(client, repo, sha) == "https://example.invalid/issues/42"


def test_issue_body_contains_update_context_and_cpu_gate() -> None:
    pinned_sha = "1" * 40
    candidate_sha = "2" * 40
    candidate = Candidate(
        kind="default-branch",
        label="main HEAD (no stable release or tag published)",
        sha=candidate_sha,
        ref="main",
        source_url=f"https://github.com/example/nca/commit/{candidate_sha}",
        published_at="2026-08-01T00:00:00Z",
    )
    comparison = {
        "status": "ahead",
        "ahead_by": 2,
        "behind_by": 0,
        "total_commits": 2,
        "commits": [
            {
                "sha": "3" * 40,
                "commit": {"message": "Add a useful feature\n\nMore context"},
            }
        ],
        "files": [
            {
                "filename": "requirements.txt",
                "status": "modified",
                "additions": 2,
                "deletions": 1,
            }
        ],
    }

    body = render_issue_body(
        upstream_repo="example/nca",
        pinned_sha=pinned_sha,
        pinned_build="219",
        candidate=candidate,
        candidate_build="220",
        comparison=comparison,
    )

    assert f"<!-- nca-upstream-sha: {candidate_sha} -->" in body
    assert "Build" not in issue_title("219", "220", pinned_sha, candidate_sha)
    assert "NCA Toolkit Build 219 -> Build 220" == issue_title(
        "219", "220", pinned_sha, candidate_sha
    ).removeprefix("chore(upstream): ")
    assert "requirements.txt" in body
    assert "torch.version.cuda is None" in body
    assert "make runtime-contract" in body
    assert "make smoke" in body
    assert "Do not update the pin blindly" in body
