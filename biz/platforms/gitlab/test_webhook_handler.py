from unittest import TestCase
from unittest.mock import patch

from biz.platforms.gitlab.webhook_handler import (
    MergeRequestHandler,
    PushHandler,
    extract_gitlab_project_ref,
    extract_gitlab_project_refs,
)


class TestExtractGitlabProjectRef(TestCase):
    def test_prefers_path_with_namespace_and_url_encodes_it(self):
        ref = extract_gitlab_project_ref(
            {
                "project": {
                    "id": 24,
                    "path_with_namespace": "group/subgroup/project",
                }
            }
        )

        self.assertEqual(ref, "group%2Fsubgroup%2Fproject")

    def test_falls_back_to_project_id_when_path_missing(self):
        ref = extract_gitlab_project_ref(
            {
                "project": {"id": 24},
                "object_attributes": {"target_project_id": 25},
            }
        )

        self.assertEqual(ref, "24")

    def test_collects_multiple_distinct_project_refs_for_fallback(self):
        refs = extract_gitlab_project_refs(
            {
                "project": {
                    "id": 24,
                    "path_with_namespace": "group/subgroup/project",
                },
                "object_attributes": {
                    "target_project_id": 24,
                    "source_project_id": 25,
                },
            }
        )

        self.assertEqual(refs, ["group%2Fsubgroup%2Fproject", "24", "25"])


class TestMergeRequestHandler(TestCase):
    @patch("biz.platforms.gitlab.webhook_handler.requests.request")
    def test_get_merge_request_commits_uses_encoded_project_path(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = "[]"
        mock_request.return_value.json.return_value = []

        handler = MergeRequestHandler(
            {
                "object_kind": "merge_request",
                "project": {"path_with_namespace": "group/subgroup/project"},
                "object_attributes": {"iid": 1930, "target_project_id": 24, "action": "open"},
            },
            "token",
            "https://gitlab.example.com",
        )

        handler.get_merge_request_commits()

        called_url = mock_request.call_args.args[1]
        self.assertIn(
            "/api/v4/projects/group%2Fsubgroup%2Fproject/merge_requests/1930/commits",
            called_url,
        )

    @patch("biz.platforms.gitlab.webhook_handler.requests.request")
    def test_get_merge_request_commits_falls_back_from_path_to_project_id(self, mock_request):
        class Response:
            def __init__(self, status_code, text, payload):
                self.status_code = status_code
                self.text = text
                self._payload = payload

            def json(self):
                return self._payload

        first_response = Response(404, '{"message":"404 Project Not Found"}', {})
        second_response = Response(200, "[]", [])
        mock_request.side_effect = [first_response, second_response]

        handler = MergeRequestHandler(
            {
                "object_kind": "merge_request",
                "project": {"id": 24, "path_with_namespace": "group/subgroup/project"},
                "object_attributes": {"iid": 1930, "target_project_id": 24, "action": "open"},
            },
            "token",
            "https://gitlab.example.com",
        )

        handler.get_merge_request_commits()

        self.assertEqual(mock_request.call_count, 2)
        self.assertIn("/projects/group%2Fsubgroup%2Fproject/", mock_request.call_args_list[0].args[1])
        self.assertIn("/projects/24/", mock_request.call_args_list[1].args[1])


class TestPushHandler(TestCase):
    @patch("biz.platforms.gitlab.webhook_handler.requests.get")
    def test_get_push_changes_uses_encoded_project_path(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = '{"diffs":[]}'
        mock_get.return_value.json.return_value = {"diffs": []}

        handler = PushHandler(
            {
                "event_name": "push",
                "project": {"path_with_namespace": "group/subgroup/project"},
                "before": "abc123",
                "after": "def456",
                "commits": [{"id": "def456"}],
            },
            "token",
            "https://gitlab.example.com",
        )

        handler.get_push_changes()

        called_url = mock_get.call_args.args[0]
        self.assertIn(
            "/api/v4/projects/group%2Fsubgroup%2Fproject/repository/compare",
            called_url,
        )
