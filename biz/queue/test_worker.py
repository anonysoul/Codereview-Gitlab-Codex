from unittest import TestCase

from biz.platforms.gitlab.review_trigger import should_review_gitlab_merge_request


class TestShouldReviewGitlabMergeRequest(TestCase):
    def test_ignore_open_action(self):
        should_review = should_review_gitlab_merge_request(
            {
                'oldrev': 'abc123',
                'last_commit': {'id': 'def456'}
            },
            'open'
        )

        self.assertFalse(should_review)

    def test_ignore_metadata_only_update(self):
        should_review = should_review_gitlab_merge_request(
            {
                'last_commit': {'id': 'def456'}
            },
            'update'
        )

        self.assertFalse(should_review)

    def test_ignore_update_without_commit_change(self):
        should_review = should_review_gitlab_merge_request(
            {
                'oldrev': 'def456',
                'last_commit': {'id': 'def456'}
            },
            'update'
        )

        self.assertFalse(should_review)

    def test_allow_update_when_commit_changes(self):
        should_review = should_review_gitlab_merge_request(
            {
                'oldrev': 'abc123',
                'last_commit': {'id': 'def456'}
            },
            'update'
        )

        self.assertTrue(should_review)
