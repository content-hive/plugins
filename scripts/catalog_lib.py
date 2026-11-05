"""Shared helpers for validating plugin repositories and generating the catalog."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent
REPOSITORIES_PATH = ROOT / "repositories.json"
REMOVED_PATH = ROOT / "removed.json"

API_URL = "https://api.github.com"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DOMAIN_PATTERN = re.compile(r"^[a-z0-9_-]+$")
REMOVED_SEVERITIES = ("removed", "critical")
MANIFEST_PATH = "plugin/manifest.json"
REPO_META_PATH = "contenthive.json"


RELEASES_PER_PAGE = 100


class RemoteDataError(Exception):
    """Raised when data fetched from a plugin repository is missing or malformed."""


class GitHubError(RemoteDataError):
    """Raised when a GitHub API request fails. ``status`` is 0 for network errors."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"GitHub API {status}: {message}" if status else f"GitHub API request failed: {message}")


def api_get(path: str, params: dict[str, str] | None = None) -> Any:
    url = f"{API_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "content-hive-plugin-catalog",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise GitHubError(e.code, f"{path}: {e.reason}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GitHubError(0, f"{path}: {e}") from e
    except ValueError as e:
        raise GitHubError(0, f"{path}: invalid JSON response ({e})") from e


def get_json_file(repository: str, path: str, ref: str) -> dict[str, Any] | None:
    """Return a JSON object file from a repository at ``ref``, or None if it does not exist."""
    try:
        data = api_get(f"/repos/{repository}/contents/{path}", {"ref": ref})
    except GitHubError as e:
        if e.status == 404:
            return None
        raise
    if not isinstance(data, dict) or not isinstance(data.get("content"), str):
        raise RemoteDataError(f"{path} at {ref} is not a file")
    try:
        content = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
    except ValueError as e:
        raise RemoteDataError(f"{path} at {ref} is not valid JSON ({e})") from e
    if not isinstance(content, dict):
        raise RemoteDataError(f"{path} at {ref} must be a JSON object")
    return content


def list_releases(repository: str) -> list[dict[str, Any]]:
    """Return all releases of a repository, following pagination."""
    releases: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = api_get(f"/repos/{repository}/releases", {"per_page": str(RELEASES_PER_PAGE), "page": str(page)})
        if not isinstance(batch, list) or not all(
            isinstance(r, dict) and isinstance(r.get("tag_name"), str) for r in batch
        ):
            raise RemoteDataError("unexpected releases response")
        releases += batch
        if len(batch) < RELEASES_PER_PAGE:
            return releases
        page += 1


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _is_version(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        Version(value)
    except InvalidVersion:
        return False
    return True


def parse_tag_version(tag: str) -> Version | None:
    if not tag.startswith("v"):
        return None
    try:
        return Version(tag[1:])
    except InvalidVersion:
        return None


def select_releases(releases: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Pick the stable release and a newer pre-release (beta) by version order.

    Draft releases and releases whose tag is not ``v<version>`` are ignored.
    """
    stable: tuple[Version, dict[str, Any]] | None = None
    beta: tuple[Version, dict[str, Any]] | None = None
    for release in releases:
        if release.get("draft"):
            continue
        version = parse_tag_version(release["tag_name"])
        if version is None:
            continue
        if release.get("prerelease"):
            if beta is None or version > beta[0]:
                beta = (version, release)
        elif stable is None or version > stable[0]:
            stable = (version, release)

    if beta and stable and beta[0] <= stable[0]:
        beta = None
    return (stable[1] if stable else None), (beta[1] if beta else None)


@dataclass
class InspectionResult:
    repository: str
    entry: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)


def _release_info(release: dict[str, Any]) -> dict[str, Any]:
    body = (release.get("body") or "").strip()
    return {
        "version": release["tag_name"][1:],
        "tag": release["tag_name"],
        "release_notes": body or None,
        "published_at": release.get("published_at"),
    }


def _check_release_files(
    repository: str, release: dict[str, Any], errors: list[str]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    tag = release["tag_name"]
    manifest = get_json_file(repository, MANIFEST_PATH, tag)
    repo_meta = get_json_file(repository, REPO_META_PATH, tag)
    if manifest is None:
        errors.append(f"{tag}: missing {MANIFEST_PATH}")
    if repo_meta is None:
        errors.append(f"{tag}: missing {REPO_META_PATH}")
    if manifest is None or repo_meta is None:
        return None

    before = len(errors)
    for key in ("domain", "name", "version"):
        if not isinstance(manifest.get(key), str) or not manifest[key]:
            errors.append(f"{tag}: {MANIFEST_PATH} missing '{key}' (non-empty string)")
    if len(errors) > before:
        return None

    domain = manifest["domain"]
    if not DOMAIN_PATTERN.match(domain):
        errors.append(f"{tag}: invalid domain '{domain}' (allowed: a-z, 0-9, -, _)")
    if tag != f"v{manifest['version']}":
        errors.append(f"{tag}: tag does not match manifest version '{manifest['version']}'")
    if repo_meta.get("domain") != domain:
        errors.append(f"{tag}: {REPO_META_PATH} domain '{repo_meta.get('domain')}' does not match manifest")
    if not isinstance(repo_meta.get("name"), str) or not repo_meta["name"]:
        errors.append(f"{tag}: {REPO_META_PATH} missing 'name'")
    if not _is_version(repo_meta.get("contenthive")):
        errors.append(f"{tag}: {REPO_META_PATH} 'contenthive' must be a valid minimum Content Hive version")
    if len(errors) > before:
        return None
    return manifest, repo_meta


def inspect_repository(repository: str) -> InspectionResult:
    """Validate a plugin repository and build its catalog entry.

    Any remote failure is recorded in ``errors`` so callers can skip this repository and continue.
    """
    result = InspectionResult(repository)
    try:
        _inspect(repository, result)
    except RemoteDataError as e:
        result.errors.append(str(e))
    if result.errors:
        result.entry = None
    return result


def _inspect(repository: str, result: InspectionResult) -> None:
    errors = result.errors
    try:
        repo = api_get(f"/repos/{repository}")
    except GitHubError as e:
        errors.append(f"repository not reachable ({e})")
        return
    if not isinstance(repo, dict):
        raise RemoteDataError("unexpected repository response")
    if repo.get("private"):
        errors.append("repository is private")
    if repo.get("archived"):
        errors.append("repository is archived")
    license_id = (repo.get("license") or {}).get("spdx_id")
    if not license_id or license_id == "NOASSERTION":
        errors.append("no license detected by GitHub")

    stable, beta = select_releases(list_releases(repository))
    if stable is None and beta is None:
        errors.append("no published release with a 'v<version>' tag")
        return

    checked = {}
    for release in (stable, beta):
        if release is not None:
            checked[release["tag_name"]] = _check_release_files(repository, release, errors)

    if stable and beta and checked.get(stable["tag_name"]) and checked.get(beta["tag_name"]):
        stable_domain = checked[stable["tag_name"]][0]["domain"]
        beta_domain = checked[beta["tag_name"]][0]["domain"]
        if stable_domain != beta_domain:
            errors.append(f"domain changed between {stable['tag_name']} and {beta['tag_name']}")

    if errors:
        return

    primary = stable or beta
    manifest, repo_meta = checked[primary["tag_name"]]
    result.entry = {
        "repository": repository,
        "domain": manifest["domain"],
        "name": manifest["name"],
        "description": manifest.get("description"),
        "author": manifest.get("author"),
        "license": license_id,
        "min_core_version": repo_meta.get("contenthive"),
        "requirements": manifest.get("requirements"),
        "disclaimer": manifest.get("disclaimer"),
        "stable": _release_info(stable) if stable else None,
        "beta": _release_info(beta) if beta else None,
    }


def check_repositories_list(repositories: Any) -> list[str]:
    """Return format errors for the contents of repositories.json."""
    if not isinstance(repositories, list) or not all(isinstance(r, str) for r in repositories):
        return ["repositories.json must be a JSON list of 'owner/repo' strings"]
    errors = [
        f"invalid repository '{r}' (expected 'owner/repo')" for r in repositories if not REPOSITORY_PATTERN.match(r)
    ]
    lowered = [r.lower() for r in repositories]
    duplicates = sorted({r for r in lowered if lowered.count(r) > 1})
    errors += [f"duplicate repository '{r}'" for r in duplicates]
    if lowered != sorted(lowered):
        errors.append("repositories.json must be sorted alphabetically")
    return errors


def check_removed_list(removed: Any) -> list[str]:
    """Return format errors for the contents of removed.json."""
    if not isinstance(removed, list):
        return ["removed.json must be a JSON list"]
    errors = []
    for i, item in enumerate(removed):
        if not isinstance(item, dict):
            errors.append(f"removed.json[{i}] must be an object")
            continue
        if not REPOSITORY_PATTERN.match(str(item.get("repository", ""))):
            errors.append(f"removed.json[{i}]: invalid 'repository'")
        if not item.get("reason"):
            errors.append(f"removed.json[{i}]: missing 'reason'")
        if item.get("severity") not in REMOVED_SEVERITIES:
            errors.append(f"removed.json[{i}]: 'severity' must be one of {', '.join(REMOVED_SEVERITIES)}")
    return errors
