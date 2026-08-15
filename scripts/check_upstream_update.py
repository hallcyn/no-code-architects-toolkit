#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"
DEFAULT_UPSTREAM_REPO = "stephengpope/no-code-architects-toolkit"
UPDATE_LABEL = "upstream-update"
PIN_PATTERN = re.compile(r"^ARG\s+NCA_UPSTREAM_COMMIT=([0-9a-f]{40})\s*$", re.MULTILINE)
PRERELEASE_PATTERN = re.compile(
    r"(^|[-_.])(alpha|beta|rc|pre|preview|dev|nightly|canary|snapshot)([-_.0-9]|$)",
    re.IGNORECASE,
)


class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Candidate:
    kind: str
    label: str
    sha: str
    ref: str
    source_url: str
    published_at: str | None = None


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = path if path.startswith("https://") else f"{API_ROOT}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "hallcyn-nca-upstream-watcher",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if data is not None:
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise GitHubAPIError(exc.code, f"GitHub API {exc.code} for {url}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API request failed for {url}: {exc}") from exc


def read_pinned_commit(dockerfile: Path) -> str:
    match = PIN_PATTERN.search(dockerfile.read_text())
    if not match:
        raise ValueError(f"NCA_UPSTREAM_COMMIT not found in {dockerfile}")
    return match.group(1)


def is_stable_tag(tag: str) -> bool:
    return PRERELEASE_PATTERN.search(tag) is None


def _repo_path(repo: str, suffix: str) -> str:
    return f"/repos/{repo}/{suffix}"


def _resolve_commit(client: GitHubClient, repo: str, ref: str) -> dict[str, Any]:
    encoded_ref = urllib.parse.quote(ref, safe="")
    return client.request_json("GET", _repo_path(repo, f"commits/{encoded_ref}"))


def select_candidate(client: GitHubClient, upstream_repo: str) -> Candidate:
    releases = client.request_json("GET", _repo_path(upstream_repo, "releases?per_page=100"))
    stable_releases = [
        release for release in releases if not release["draft"] and not release["prerelease"]
    ]
    if stable_releases:
        release = max(
            stable_releases,
            key=lambda item: item.get("published_at") or item.get("created_at") or "",
        )
        commit = _resolve_commit(client, upstream_repo, release["tag_name"])
        return Candidate(
            kind="release",
            label=f"release {release['tag_name']}",
            sha=commit["sha"],
            ref=release["tag_name"],
            source_url=release["html_url"],
            published_at=release.get("published_at"),
        )

    tags = client.request_json("GET", _repo_path(upstream_repo, "tags?per_page=100"))
    stable_tags = [tag for tag in tags if is_stable_tag(tag["name"])]
    if stable_tags:
        dated_tags: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for tag in stable_tags[:25]:
            commit = _resolve_commit(client, upstream_repo, tag["commit"]["sha"])
            commit_date = (
                commit["commit"]["committer"].get("date")
                or commit["commit"]["author"].get("date")
                or ""
            )
            dated_tags.append((commit_date, tag, commit))
        commit_date, tag, commit = max(dated_tags, key=lambda item: item[0])
        return Candidate(
            kind="tag",
            label=f"tag {tag['name']}",
            sha=commit["sha"],
            ref=tag["name"],
            source_url=f"https://github.com/{upstream_repo}/releases/tag/{tag['name']}",
            published_at=commit_date,
        )

    repo = client.request_json("GET", _repo_path(upstream_repo, ""))
    default_branch = repo["default_branch"]
    commit = _resolve_commit(client, upstream_repo, default_branch)
    commit_date = (
        commit["commit"]["committer"].get("date") or commit["commit"]["author"].get("date") or None
    )
    return Candidate(
        kind="default-branch",
        label=f"{default_branch} HEAD (no stable release or tag published)",
        sha=commit["sha"],
        ref=default_branch,
        source_url=commit["html_url"],
        published_at=commit_date,
    )


def get_build_number(client: GitHubClient, repo: str, sha: str) -> str | None:
    encoded_sha = urllib.parse.quote(sha, safe="")
    try:
        data = client.request_json(
            "GET",
            _repo_path(repo, f"contents/build_number.txt?ref={encoded_sha}"),
        )
    except GitHubAPIError as exc:
        if exc.status == 404:
            return None
        raise

    if data.get("encoding") != "base64" or "content" not in data:
        return None
    value = base64.b64decode(data["content"]).decode().strip()
    return value or None


def compare_commits(
    client: GitHubClient,
    repo: str,
    pinned_sha: str,
    candidate_sha: str,
) -> dict[str, Any] | None:
    if pinned_sha == candidate_sha:
        return {
            "status": "identical",
            "ahead_by": 0,
            "behind_by": 0,
            "total_commits": 0,
            "commits": [],
            "files": [],
        }
    try:
        return client.request_json(
            "GET",
            _repo_path(repo, f"compare/{pinned_sha}...{candidate_sha}"),
        )
    except GitHubAPIError as exc:
        if exc.status in {404, 409, 422}:
            return None
        raise


def should_open_update(
    pinned_sha: str,
    candidate_sha: str,
    comparison: dict[str, Any] | None,
) -> bool:
    if pinned_sha == candidate_sha:
        return False
    if comparison is None:
        return True
    return comparison.get("status") not in {"identical", "behind"}


def _commit_subject(commit: dict[str, Any]) -> str:
    message = commit.get("commit", {}).get("message", "")
    return message.splitlines()[0].replace("`", "'") or "(no commit message)"


def _build_label(build_number: str | None, sha: str) -> str:
    return f"Build {build_number}" if build_number else sha[:12]


def issue_title(
    pinned_build: str | None,
    candidate_build: str | None,
    pinned_sha: str,
    candidate_sha: str,
) -> str:
    before = _build_label(pinned_build, pinned_sha)
    after = _build_label(candidate_build, candidate_sha)
    return f"chore(upstream): NCA Toolkit {before} -> {after}"


def render_issue_body(
    *,
    upstream_repo: str,
    pinned_sha: str,
    pinned_build: str | None,
    candidate: Candidate,
    candidate_build: str | None,
    comparison: dict[str, Any] | None,
) -> str:
    compare_url = f"https://github.com/{upstream_repo}/compare/{pinned_sha}...{candidate.sha}"
    marker = f"<!-- nca-upstream-sha: {candidate.sha} -->"

    if comparison is None:
        relation = "unknown (GitHub could not produce a compare result)"
        ahead_by = "unknown"
        behind_by = "unknown"
        total_commits = "unknown"
        commits: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
    else:
        relation = str(comparison.get("status", "unknown"))
        ahead_by = str(comparison.get("ahead_by", "unknown"))
        behind_by = str(comparison.get("behind_by", "unknown"))
        total_commits = str(comparison.get("total_commits", "unknown"))
        commits = comparison.get("commits", [])
        files = comparison.get("files", [])

    commit_lines = []
    for commit in commits[:20]:
        commit_lines.append(f"- `{commit['sha'][:12]}` {_commit_subject(commit)}")
    if len(commits) > 20:
        commit_lines.append(f"- ... plus {len(commits) - 20} more commit(s)")
    commit_section = "\n".join(commit_lines) if commit_lines else "- No commit list available."

    file_lines = []
    for file in files[:30]:
        file_lines.append(
            "- `{filename}` — {status}, +{additions}/-{deletions}".format(
                filename=file["filename"],
                status=file.get("status", "changed"),
                additions=file.get("additions", 0),
                deletions=file.get("deletions", 0),
            )
        )
    if len(files) > 30:
        file_lines.append(f"- ... plus {len(files) - 30} more changed file(s)")
    file_section = "\n".join(file_lines) if file_lines else "- No changed-file list available."

    published_line = candidate.published_at or "not available"
    return f"""{marker}
## Automated upstream update notice

The monthly watcher found a newer NCA Toolkit source candidate than the commit pinned by this Railway CPU wrapper.

### Current pin

- Source: `{upstream_repo}`
- Commit: [`{pinned_sha}`](https://github.com/{upstream_repo}/commit/{pinned_sha})
- Upstream build: `{pinned_build or "not available"}`

### Candidate

- Selection mode: **{candidate.label}**
- Ref: `{candidate.ref}`
- Commit: [`{candidate.sha}`](https://github.com/{upstream_repo}/commit/{candidate.sha})
- Upstream build: `{candidate_build or "not available"}`
- Published/committed: `{published_line}`
- Source: {candidate.source_url}

### Comparison

- Relationship: `{relation}`
- Commits ahead: `{ahead_by}`
- Commits behind: `{behind_by}`
- Total commits in comparison: `{total_commits}`
- Full diff: {compare_url}

#### Commit summary

{commit_section}

#### Changed files

{file_section}

## CPU / Railway safety gate

Upstream does **not** publish a separate CPU build for this wrapper. This repository creates the CPU deployment by installing PyTorch from the CPU-only index and then validating the resulting runtime. Do not update the pin blindly.

Before merging an update PR:

- [ ] Review the upstream comparison above for API, dependency, storage and security changes.
- [ ] Update only `NCA_UPSTREAM_COMMIT` to the intended upstream commit.
- [ ] Check upstream dependency changes for anything that could reintroduce CUDA/NVIDIA packages.
- [ ] Run `make check`.
- [ ] Build from scratch with `docker compose build --no-cache` when dependency/runtime files changed upstream.
- [ ] Run `make runtime-contract` and confirm `torch.version.cuda is None`.
- [ ] Confirm the baked Whisper model still loads from the image cache.
- [ ] Confirm Playwright launches Chromium successfully.
- [ ] Confirm the required FFmpeg codecs/filters still pass the runtime contract.
- [ ] Run `make smoke` and verify health/authentication behavior.
- [ ] Let the GitHub runtime smoke workflow pass before merging.

## Suggested task for the update PR

Review this issue and the upstream diff. If the candidate is safe for the Railway CPU deployment, update `NCA_UPSTREAM_COMMIT`, adapt the wrapper only if upstream behavior requires it, run all fast and runtime checks, and open a PR that links this issue. Do not weaken the CPU-only or security guarantees to make the update pass.

---

Generated by `.github/workflows/upstream-check.yml` on the monthly upstream-maintenance cycle.
"""


def existing_issue_url(client: GitHubClient, target_repo: str, candidate_sha: str) -> str | None:
    marker = f"<!-- nca-upstream-sha: {candidate_sha} -->"
    for page in range(1, 21):
        issues = client.request_json(
            "GET",
            _repo_path(target_repo, f"issues?state=all&per_page=100&page={page}"),
        )
        for issue in issues:
            if "pull_request" in issue:
                continue
            if marker in (issue.get("body") or ""):
                return issue["html_url"]
        if len(issues) < 100:
            break
    return None


def ensure_update_label(client: GitHubClient, target_repo: str) -> None:
    encoded_label = urllib.parse.quote(UPDATE_LABEL, safe="")
    try:
        client.request_json("GET", _repo_path(target_repo, f"labels/{encoded_label}"))
        return
    except GitHubAPIError as exc:
        if exc.status != 404:
            raise

    client.request_json(
        "POST",
        _repo_path(target_repo, "labels"),
        {
            "name": UPDATE_LABEL,
            "color": "1D76DB",
            "description": "Automated notices for new NCA Toolkit upstream versions",
        },
    )


def create_update_issue(
    client: GitHubClient,
    target_repo: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    return client.request_json(
        "POST",
        _repo_path(target_repo, "issues"),
        {"title": title, "body": body, "labels": [UPDATE_LABEL]},
    )


def write_job_summary(message: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a") as summary:
            summary.write(message.rstrip() + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the pinned NCA upstream revision for updates"
    )
    parser.add_argument("--dockerfile", type=Path, default=Path("Dockerfile"))
    parser.add_argument("--upstream-repo", default=DEFAULT_UPSTREAM_REPO)
    parser.add_argument("--target-repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report an available update without reading or creating issues",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    client = GitHubClient(token)

    pinned_sha = read_pinned_commit(args.dockerfile)
    candidate = select_candidate(client, args.upstream_repo)
    pinned_build = get_build_number(client, args.upstream_repo, pinned_sha)
    candidate_build = get_build_number(client, args.upstream_repo, candidate.sha)
    comparison = compare_commits(client, args.upstream_repo, pinned_sha, candidate.sha)

    current_label = _build_label(pinned_build, pinned_sha)
    candidate_label = _build_label(candidate_build, candidate.sha)
    if not should_open_update(pinned_sha, candidate.sha, comparison):
        message = (
            "## NCA upstream check\n\n"
            f"No update issue needed. Current pin: **{current_label}** (`{pinned_sha[:12]}`). "
            f"Selected upstream candidate: **{candidate_label}** (`{candidate.sha[:12]}`) via "
            f"**{candidate.label}**."
        )
        print(message.replace("## NCA upstream check\n\n", ""))
        write_job_summary(message)
        return 0

    title = issue_title(pinned_build, candidate_build, pinned_sha, candidate.sha)
    body = render_issue_body(
        upstream_repo=args.upstream_repo,
        pinned_sha=pinned_sha,
        pinned_build=pinned_build,
        candidate=candidate,
        candidate_build=candidate_build,
        comparison=comparison,
    )

    if args.dry_run:
        print(f"Update available: {title}")
        print(f"Candidate: {candidate.sha} via {candidate.label}")
        write_job_summary(
            "## NCA upstream check\n\n"
            f"Dry-run detected an update: **{title}**. No issue was created."
        )
        return 0

    if not token:
        raise RuntimeError("GITHUB_TOKEN or GH_TOKEN is required when creating an issue")
    if not args.target_repo:
        raise RuntimeError("--target-repo or GITHUB_REPOSITORY is required when creating an issue")

    duplicate = existing_issue_url(client, args.target_repo, candidate.sha)
    if duplicate:
        print(f"Update already tracked: {duplicate}")
        write_job_summary(
            f"## NCA upstream check\n\nUpdate **{candidate_label}** is already tracked: {duplicate}"
        )
        return 0

    ensure_update_label(client, args.target_repo)
    issue = create_update_issue(client, args.target_repo, title, body)
    print(f"Created upstream update issue: {issue['html_url']}")
    write_job_summary(
        "## NCA upstream check\n\n"
        f"Created update issue for **{candidate_label}**: {issue['html_url']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
