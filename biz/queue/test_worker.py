import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.modules.setdefault(
    "pandas",
    SimpleNamespace(DataFrame=object, read_sql_query=lambda *args, **kwargs: None),
)

from biz.platforms.gitlab.review_trigger import should_review_gitlab_merge_request
from biz.queue.worker import handle_merge_request_event


class TestShouldReviewGitlabMergeRequest(TestCase):
    def test_allow_open_action_with_last_commit(self):
        should_review = should_review_gitlab_merge_request(
            {
                'last_commit': {'id': 'def456'}
            },
            'open'
        )

        self.assertTrue(should_review)

    def test_ignore_update_without_last_commit(self):
        should_review = should_review_gitlab_merge_request(
            {},
            'update'
        )

        self.assertFalse(should_review)

    def test_allow_update_without_oldrev(self):
        should_review = should_review_gitlab_merge_request(
            {
                'last_commit': {'id': 'def456'}
            },
            'update',
            {'last_commit': {'previous': {'id': 'abc123'}, 'current': {'id': 'def456'}}},
        )

        self.assertTrue(should_review)

    def test_allow_update_when_commit_changes(self):
        should_review = should_review_gitlab_merge_request(
            {
                'oldrev': 'abc123',
                'last_commit': {'id': 'def456'}
            },
            'update',
        )

        self.assertTrue(should_review)

    def test_ignore_update_without_oldrev_or_last_commit_change(self):
        should_review = should_review_gitlab_merge_request(
            {
                'last_commit': {'id': 'def456'}
            },
            'update',
            {'updated_at': {'previous': '1', 'current': '2'}},
        )

        self.assertFalse(should_review)

    def test_ignore_non_reviewable_action(self):
        should_review = should_review_gitlab_merge_request(
            {
                'last_commit': {'id': 'def456'}
            },
            'merge'
        )

        self.assertFalse(should_review)


class TestHandleMergeRequestEvent(TestCase):
    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    @patch("biz.queue.worker.CodexReviewRunner")
    @patch("biz.queue.worker.GitLabRepoCacheManager")
    @patch("biz.queue.worker.MergeRequestHandler")
    def test_mr_review_uses_codex_and_writes_fixed_score(
        self,
        handler_cls,
        repo_cache_cls,
        codex_runner_cls,
        _check_exists,
    ):
        handler = MagicMock()
        handler.action = "update"
        handler.target_branch_protected.return_value = True
        handler.get_merge_request_commits.return_value = [{"title": "feat", "message": "feat"}]
        handler_cls.return_value = handler

        repo_cache = MagicMock()
        repo_cache.prepare_merge_request_repo.return_value = SimpleNamespace(
            local_path="/tmp/repo",
            source_branch="feature/test",
            target_branch="main",
            last_commit_id="newrev",
            base_ref="origin/main",
        )
        repo_cache.collect_diff_stats.return_value = SimpleNamespace(
            additions=10,
            deletions=2,
            changed_files=["a.py"],
        )
        repo_cache_cls.return_value = repo_cache

        codex_runner = MagicMock()
        codex_runner.review.return_value = "review result"
        codex_runner_cls.return_value = codex_runner

        signal = MagicMock()
        webhook_data = {
            "project": {"name": "demo"},
            "user": {"username": "alice"},
            "object_attributes": {
                "action": "update",
                "oldrev": "oldrev",
                "last_commit": {"id": "newrev"},
                "source_branch": "feature/test",
                "target_branch": "main",
                "url": "https://gitlab.example.com/demo/-/merge_requests/1",
            },
        }

        with patch("biz.queue.worker.event_manager", {"merge_request_reviewed": signal}):
            handle_merge_request_event(webhook_data, "token", "https://gitlab.example.com", "gitlab_example")

        handler.add_merge_request_notes.assert_called_once_with("review result")
        codex_runner.review.assert_called_once_with("/tmp/repo", "origin/main")
        sent_entity = signal.send.call_args.args[0]
        self.assertEqual(sent_entity.score, 0)
        self.assertEqual(sent_entity.additions, 10)
        self.assertEqual(sent_entity.deletions, 2)

    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    @patch("biz.queue.worker.CodexReviewRunner")
    @patch("biz.queue.worker.GitLabRepoCacheManager")
    @patch("biz.queue.worker.MergeRequestHandler")
    def test_mr_review_replies_with_failure_note_when_codex_fails(
        self,
        handler_cls,
        repo_cache_cls,
        codex_runner_cls,
        _check_exists,
    ):
        handler = MagicMock()
        handler.action = "update"
        handler.target_branch_protected.return_value = True
        handler.get_merge_request_commits.return_value = [{"title": "feat", "message": "feat"}]
        handler_cls.return_value = handler

        repo_cache = MagicMock()
        repo_cache.prepare_merge_request_repo.return_value = SimpleNamespace(
            local_path="/tmp/repo",
            source_branch="feature/test",
            target_branch="main",
            last_commit_id="newrev",
            base_ref="origin/main",
        )
        repo_cache.collect_diff_stats.return_value = SimpleNamespace(
            additions=10,
            deletions=2,
            changed_files=["a.py"],
        )
        repo_cache_cls.return_value = repo_cache

        codex_runner = MagicMock()
        codex_runner.review.side_effect = RuntimeError("boom")
        codex_runner_cls.return_value = codex_runner

        webhook_data = {
            "project": {"name": "demo"},
            "user": {"username": "alice"},
            "object_attributes": {
                "action": "update",
                "oldrev": "oldrev",
                "last_commit": {"id": "newrev"},
                "source_branch": "feature/test",
                "target_branch": "main",
                "url": "https://gitlab.example.com/demo/-/merge_requests/1",
            },
        }

        with patch("biz.queue.worker.event_manager", {"merge_request_reviewed": MagicMock()}):
            handle_merge_request_event(webhook_data, "token", "https://gitlab.example.com", "gitlab_example")

        failure_note = handler.add_merge_request_notes.call_args.args[0]
        self.assertIn("自动审查失败", failure_note)

    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    @patch("biz.queue.worker.CodexReviewRunner")
    @patch("biz.queue.worker.GitLabRepoCacheManager")
    @patch("biz.queue.worker.MergeRequestHandler")
    def test_mr_review_continues_even_without_diff_files(
        self,
        handler_cls,
        repo_cache_cls,
        codex_runner_cls,
        _check_exists,
    ):
        handler = MagicMock()
        handler.action = "update"
        handler.target_branch_protected.return_value = True
        handler.get_merge_request_commits.return_value = [{"title": "docs", "message": "docs"}]
        handler_cls.return_value = handler

        repo_cache = MagicMock()
        repo_cache.prepare_merge_request_repo.return_value = SimpleNamespace(
            local_path="/tmp/repo",
            source_branch="feature/test",
            target_branch="main",
            last_commit_id="newrev",
            base_ref="origin/main",
        )
        repo_cache.collect_diff_stats.return_value = SimpleNamespace(
            additions=0,
            deletions=0,
            changed_files=[],
        )
        repo_cache_cls.return_value = repo_cache

        codex_runner = MagicMock()
        codex_runner.review.return_value = "review result"
        codex_runner_cls.return_value = codex_runner

        webhook_data = {
            "project": {"name": "demo"},
            "user": {"username": "alice"},
            "object_attributes": {
                "action": "update",
                "last_commit": {"id": "newrev"},
                "source_branch": "feature/test",
                "target_branch": "main",
                "url": "https://gitlab.example.com/demo/-/merge_requests/1",
            },
            "changes": {
                "last_commit": {"previous": {"id": "oldrev"}, "current": {"id": "newrev"}},
            },
        }

        with patch("biz.queue.worker.event_manager", {"merge_request_reviewed": MagicMock()}):
            handle_merge_request_event(webhook_data, "token", "https://gitlab.example.com", "gitlab_example")

        codex_runner.review.assert_called_once_with("/tmp/repo", "origin/main")
        handler.add_merge_request_notes.assert_called_once_with("review result")

    @patch("biz.queue.worker.ReviewService.check_mr_last_commit_id_exists", return_value=False)
    @patch("biz.queue.worker.CodexReviewRunner")
    @patch("biz.queue.worker.GitLabRepoCacheManager")
    @patch("biz.queue.worker.MergeRequestHandler")
    def test_mr_review_falls_back_to_webhook_last_commit_when_commits_api_fails(
        self,
        handler_cls,
        repo_cache_cls,
        codex_runner_cls,
        _check_exists,
    ):
        handler = MagicMock()
        handler.action = "update"
        handler.target_branch_protected.return_value = True
        handler.get_merge_request_commits.return_value = []
        handler_cls.return_value = handler

        repo_cache = MagicMock()
        repo_cache.prepare_merge_request_repo.return_value = SimpleNamespace(
            local_path="/tmp/repo",
            source_branch="feature/test",
            target_branch="main",
            last_commit_id="newrev",
            base_ref="origin/main",
        )
        repo_cache.collect_diff_stats.return_value = SimpleNamespace(
            additions=10,
            deletions=2,
            changed_files=["a.py"],
        )
        repo_cache_cls.return_value = repo_cache

        codex_runner = MagicMock()
        codex_runner.review.return_value = "review result"
        codex_runner_cls.return_value = codex_runner

        signal = MagicMock()
        webhook_data = {
            "project": {"name": "demo"},
            "user": {"username": "alice"},
            "object_attributes": {
                "action": "update",
                "oldrev": "oldrev",
                "last_commit": {
                    "id": "newrev",
                    "title": "feat: fallback",
                    "message": "feat: fallback\n",
                },
                "source_branch": "feature/test",
                "target_branch": "main",
                "url": "https://gitlab.example.com/demo/-/merge_requests/1",
            },
        }

        with patch("biz.queue.worker.event_manager", {"merge_request_reviewed": signal}):
            handle_merge_request_event(webhook_data, "token", "https://gitlab.example.com", "gitlab_example")

        sent_entity = signal.send.call_args.args[0]
        self.assertEqual(sent_entity.commits, [webhook_data["object_attributes"]["last_commit"]])
        handler.add_merge_request_notes.assert_called_once_with("review result")
