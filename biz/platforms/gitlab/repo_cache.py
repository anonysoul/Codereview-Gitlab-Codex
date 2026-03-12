import base64
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin

import requests

from biz.platforms.gitlab.webhook_handler import slugify_url
from biz.utils.log import logger


DEFAULT_CACHE_DIR = "~/.cache/codereview"


@dataclass
class RepoPreparationResult:
    local_path: str
    project_path: str
    clone_url: str
    target_branch: str
    source_branch: str
    last_commit_id: str
    base_ref: str


@dataclass
class RepoDiffStats:
    additions: int
    deletions: int
    changed_files: list[str]


def get_cache_root() -> Path:
    cache_dir = os.getenv("CODEREVIEW_CACHE_DIR", DEFAULT_CACHE_DIR)
    return Path(os.path.expanduser(cache_dir)).resolve()


def build_repo_cache_dirname(gitlab_url: str, project_path: str) -> str:
    host_slug = slugify_url(gitlab_url.rstrip("/"))
    project_slug = slugify_url(project_path.strip("/"))
    return f"{host_slug}__{project_slug}"


class GitLabRepoCacheManager:
    def __init__(self, gitlab_url: str, gitlab_token: str):
        self.gitlab_url = gitlab_url.rstrip("/")
        self.gitlab_token = gitlab_token

    def prepare_merge_request_repo(self, webhook_data: dict) -> RepoPreparationResult:
        object_attributes = webhook_data.get("object_attributes", {})
        target_branch = object_attributes.get("target_branch", "")
        source_branch = object_attributes.get("source_branch", "")
        last_commit_id = object_attributes.get("last_commit", {}).get("id", "")
        project_id = self._get_project_id(webhook_data)

        if not project_id:
            raise ValueError("Missing GitLab project id in merge request webhook payload.")
        if not target_branch or not source_branch:
            raise ValueError("Missing source or target branch in merge request webhook payload.")
        if not last_commit_id:
            raise ValueError("Missing last_commit.id in merge request webhook payload.")

        project_info = self._get_project_info(webhook_data, project_id)
        project_path = project_info["project_path"]
        clone_url = project_info["clone_url"]
        local_path = self._ensure_repo(clone_url, project_path)

        self._sync_merge_request_refs(local_path, target_branch, source_branch, last_commit_id)

        return RepoPreparationResult(
            local_path=str(local_path),
            project_path=project_path,
            clone_url=clone_url,
            target_branch=target_branch,
            source_branch=source_branch,
            last_commit_id=last_commit_id,
            base_ref=self.build_base_ref(target_branch),
        )

    def collect_diff_stats(self, repo_path: str, target_branch: str) -> RepoDiffStats:
        base_ref = self.build_base_ref(target_branch)
        changed_files = self._list_changed_files(repo_path, base_ref)
        additions, deletions = self._collect_numstat(repo_path, base_ref, changed_files)
        return RepoDiffStats(
            additions=additions,
            deletions=deletions,
            changed_files=changed_files,
        )

    def build_base_ref(self, target_branch: str) -> str:
        return f"origin/{target_branch}"

    def _get_project_id(self, webhook_data: dict):
        project = webhook_data.get("project", {})
        object_attributes = webhook_data.get("object_attributes", {})
        return (
            project.get("id")
            or object_attributes.get("target_project_id")
            or object_attributes.get("source_project_id")
        )

    def _get_project_info(self, webhook_data: dict, project_id) -> dict:
        project = webhook_data.get("project", {})
        object_attributes = webhook_data.get("object_attributes", {})

        project_path = (
            project.get("path_with_namespace")
            or object_attributes.get("target", {}).get("path_with_namespace")
            or object_attributes.get("source", {}).get("path_with_namespace")
        )
        clone_url = (
            project.get("git_http_url")
            or project.get("http_url")
            or webhook_data.get("repository", {}).get("git_http_url")
            or webhook_data.get("repository", {}).get("homepage")
        )

        if project_path and clone_url:
            return {
                "project_path": project_path,
                "clone_url": self._normalize_clone_url(clone_url),
            }

        api_project = self._fetch_project(project_id)
        api_project_path = api_project.get("path_with_namespace")
        api_clone_url = api_project.get("http_url_to_repo")
        if not api_project_path or not api_clone_url:
            raise ValueError(f"Failed to resolve GitLab project info for project_id={project_id}.")

        return {
            "project_path": api_project_path,
            "clone_url": self._normalize_clone_url(api_clone_url),
        }

    def _fetch_project(self, project_id) -> dict:
        project_ref = quote(str(project_id), safe="")
        url = urljoin(f"{self.gitlab_url}/", f"api/v4/projects/{project_ref}")
        headers = {"Private-Token": self.gitlab_token}
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        logger.debug("Get project response from gitlab: %s, %s", response.status_code, response.text)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to get project info from GitLab: {response.status_code}, {response.text}"
            )
        return response.json()

    def _normalize_clone_url(self, clone_url: str) -> str:
        if clone_url.endswith(".git"):
            return clone_url
        return f"{clone_url.rstrip('/')}.git"

    def _ensure_repo(self, clone_url: str, project_path: str) -> Path:
        cache_root = get_cache_root()
        cache_root.mkdir(parents=True, exist_ok=True)
        repo_dir = cache_root / build_repo_cache_dirname(self.gitlab_url, project_path)

        if not (repo_dir / ".git").exists():
            logger.info("Cloning GitLab repository into cache: %s", repo_dir)
            self._run_git(
                ["clone", clone_url, str(repo_dir)],
                cwd=cache_root,
            )
            return repo_dir

        logger.info("Refreshing cached GitLab repository: %s", repo_dir)
        self._run_git(["remote", "set-url", "origin", clone_url], cwd=repo_dir)
        self._run_git(["fetch", "--prune", "origin"], cwd=repo_dir)
        return repo_dir

    def _sync_merge_request_refs(
        self,
        repo_dir: Path,
        target_branch: str,
        source_branch: str,
        last_commit_id: str,
    ):
        self._run_git(
            ["fetch", "--prune", "origin", target_branch, source_branch],
            cwd=repo_dir,
        )
        self._run_git(["checkout", "--force", last_commit_id], cwd=repo_dir)
        self._run_git(["clean", "-fd"], cwd=repo_dir)

    def _list_changed_files(self, repo_path: str, base_ref: str) -> list[str]:
        result = self._run_git(
            ["diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...HEAD"],
            cwd=Path(repo_path),
        )
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return files

    def _collect_numstat(self, repo_path: str, base_ref: str, changed_files: list[str]) -> tuple[int, int]:
        if not changed_files:
            return 0, 0

        result = self._run_git(
            ["diff", "--numstat", "--diff-filter=ACMR", f"{base_ref}...HEAD"],
            cwd=Path(repo_path),
        )
        additions = 0
        deletions = 0
        changed_file_set = set(changed_files)

        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added, deleted, path = parts[0], parts[1], parts[2]
            if path not in changed_file_set:
                continue
            additions += 0 if added == "-" else int(added)
            deletions += 0 if deleted == "-" else int(deleted)

        return additions, deletions

    def _git_env(self) -> dict:
        env = os.environ.copy()
        auth = base64.b64encode(f"oauth2:{self.gitlab_token}".encode("utf-8")).decode("ascii")
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_HTTP_EXTRA_HEADER"] = f"AUTHORIZATION: Basic {auth}"
        return env

    def _run_git(self, args: list[str], cwd: Path):
        command = ["git", *args]
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=self._git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: {' '.join(command)}\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )
        return result
