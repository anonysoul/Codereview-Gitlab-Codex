import os
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from biz.platforms.gitlab.repo_cache import (
    GitLabRepoCacheManager,
    build_repo_cache_dirname,
)


def run_git(args: list[str], cwd: Path):
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


class TestGitLabRepoCacheManager(TestCase):
    def test_build_repo_cache_dirname_is_stable(self):
        dirname = build_repo_cache_dirname(
            "https://gitlab.example.com/",
            "group/subgroup/project",
        )

        self.assertEqual(
            dirname,
            "gitlab_example_com__group_subgroup_project",
        )

    def test_prepare_merge_request_repo_clones_and_checks_out_last_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            remote_repo = tmp_path / "remote.git"
            worktree = tmp_path / "worktree"
            cache_dir = tmp_path / "cache"

            run_git(["init", "--bare", str(remote_repo)], cwd=tmp_path)
            run_git(["clone", str(remote_repo), str(worktree)], cwd=tmp_path)
            run_git(["config", "user.name", "tester"], cwd=worktree)
            run_git(["config", "user.email", "tester@example.com"], cwd=worktree)

            (worktree / "README.md").write_text("base\n", encoding="utf-8")
            run_git(["add", "README.md"], cwd=worktree)
            run_git(["commit", "-m", "base"], cwd=worktree)
            run_git(["branch", "-M", "main"], cwd=worktree)
            run_git(["push", "-u", "origin", "main"], cwd=worktree)

            run_git(["checkout", "-b", "feature/test"], cwd=worktree)
            (worktree / "feature.txt").write_text("feature\n", encoding="utf-8")
            run_git(["add", "feature.txt"], cwd=worktree)
            run_git(["commit", "-m", "feature"], cwd=worktree)
            last_commit_id = run_git(["rev-parse", "HEAD"], cwd=worktree)
            run_git(["push", "-u", "origin", "feature/test"], cwd=worktree)

            manager = GitLabRepoCacheManager("https://gitlab.example.com", "token")
            webhook_data = {
                "project": {
                    "id": 1,
                    "path_with_namespace": "group/project",
                    "git_http_url": str(remote_repo),
                },
                "object_attributes": {
                    "target_project_id": 1,
                    "source_branch": "feature/test",
                    "target_branch": "main",
                    "last_commit": {"id": last_commit_id},
                },
            }

            with patch.dict(os.environ, {"CODEREVIEW_CACHE_DIR": str(cache_dir)}, clear=False):
                prepared = manager.prepare_merge_request_repo(webhook_data)

            repo_path = Path(prepared.local_path)
            self.assertTrue((repo_path / ".git").exists())
            self.assertEqual(run_git(["rev-parse", "HEAD"], cwd=repo_path), last_commit_id)

    def test_prepare_merge_request_repo_fetches_existing_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            remote_repo = tmp_path / "remote.git"
            worktree = tmp_path / "worktree"
            cache_dir = tmp_path / "cache"

            run_git(["init", "--bare", str(remote_repo)], cwd=tmp_path)
            run_git(["clone", str(remote_repo), str(worktree)], cwd=tmp_path)
            run_git(["config", "user.name", "tester"], cwd=worktree)
            run_git(["config", "user.email", "tester@example.com"], cwd=worktree)

            (worktree / "README.md").write_text("base\n", encoding="utf-8")
            run_git(["add", "README.md"], cwd=worktree)
            run_git(["commit", "-m", "base"], cwd=worktree)
            run_git(["branch", "-M", "main"], cwd=worktree)
            run_git(["push", "-u", "origin", "main"], cwd=worktree)

            run_git(["checkout", "-b", "feature/test"], cwd=worktree)
            (worktree / "feature.txt").write_text("v1\n", encoding="utf-8")
            run_git(["add", "feature.txt"], cwd=worktree)
            run_git(["commit", "-m", "feature v1"], cwd=worktree)
            first_commit_id = run_git(["rev-parse", "HEAD"], cwd=worktree)
            run_git(["push", "-u", "origin", "feature/test"], cwd=worktree)

            manager = GitLabRepoCacheManager("https://gitlab.example.com", "token")
            webhook_data = {
                "project": {
                    "id": 1,
                    "path_with_namespace": "group/project",
                    "git_http_url": str(remote_repo),
                },
                "object_attributes": {
                    "target_project_id": 1,
                    "source_branch": "feature/test",
                    "target_branch": "main",
                    "last_commit": {"id": first_commit_id},
                },
            }

            with patch.dict(os.environ, {"CODEREVIEW_CACHE_DIR": str(cache_dir)}, clear=False):
                manager.prepare_merge_request_repo(webhook_data)

            (worktree / "feature.txt").write_text("v2\n", encoding="utf-8")
            run_git(["add", "feature.txt"], cwd=worktree)
            run_git(["commit", "-m", "feature v2"], cwd=worktree)
            second_commit_id = run_git(["rev-parse", "HEAD"], cwd=worktree)
            run_git(["push", "origin", "feature/test"], cwd=worktree)
            webhook_data["object_attributes"]["last_commit"]["id"] = second_commit_id

            with patch.dict(os.environ, {"CODEREVIEW_CACHE_DIR": str(cache_dir)}, clear=False):
                prepared = manager.prepare_merge_request_repo(webhook_data)

            self.assertEqual(
                run_git(["rev-parse", "HEAD"], cwd=Path(prepared.local_path)),
                second_commit_id,
            )

    @patch("biz.platforms.gitlab.repo_cache.requests.get")
    def test_prepare_merge_request_repo_falls_back_to_gitlab_api(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "{}"
        mock_get.return_value.json.return_value = {
            "path_with_namespace": "group/project",
            "http_url_to_repo": "https://gitlab.example.com/group/project.git",
        }

        manager = GitLabRepoCacheManager("https://gitlab.example.com", "token")
        webhook_data = {
            "project": {"id": 123},
            "object_attributes": {
                "target_project_id": 123,
                "source_branch": "feature/test",
                "target_branch": "main",
                "last_commit": {"id": "abc123"},
            },
        }

        with patch.object(manager, "_ensure_repo", return_value=Path("/tmp/repo")):
            with patch.object(manager, "_sync_merge_request_refs") as sync_mock:
                prepared = manager.prepare_merge_request_repo(webhook_data)

        self.assertEqual(prepared.project_path, "group/project")
        self.assertEqual(prepared.clone_url, "https://gitlab.example.com/group/project.git")
        sync_mock.assert_called_once_with(Path("/tmp/repo"), "main", "feature/test", "abc123")
