import os
from io import StringIO
from unittest import TestCase
from unittest.mock import MagicMock, patch

from biz.utils.codex_runner import CodexReviewRunner


class TestCodexReviewRunner(TestCase):
    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.logger")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_returns_stdout(self, mock_popen, mock_logger, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("review result\n")
        process.stderr = StringIO("progress line\n")
        process.wait.return_value = 0
        mock_popen.return_value = process

        result = CodexReviewRunner(prompt="custom prompt").review("/tmp/repo", "origin/main")

        self.assertEqual(result, "review result")
        mock_popen.assert_called_once()
        mock_logger.info.assert_any_call("codex review: %s", "review result")
        mock_logger.warning.assert_any_call("codex review: %s", "progress line")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_raises_when_codex_fails(self, mock_popen, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("")
        process.stderr = StringIO("boom\n")
        process.wait.return_value = 1
        mock_popen.return_value = process

        with self.assertRaisesRegex(RuntimeError, "Codex review failed"):
            CodexReviewRunner().review("/tmp/repo", "origin/main")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_raises_when_output_is_empty(self, mock_popen, _mock_which):
        process = MagicMock()
        process.stdout = StringIO(" \n")
        process.stderr = StringIO("")
        process.wait.return_value = 0
        mock_popen.return_value = process

        with self.assertRaisesRegex(RuntimeError, "empty output"):
            CodexReviewRunner().review("/tmp/repo", "origin/main")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_uses_env_prompt_when_present(self, mock_popen, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("ok")
        process.stderr = StringIO("")
        process.wait.return_value = 0
        mock_popen.return_value = process

        with patch.dict(os.environ, {"CODEX_REVIEW_PROMPT": "env prompt"}, clear=False):
            CodexReviewRunner().review("/tmp/repo", "origin/main")

        command = mock_popen.call_args.args[0]
        self.assertEqual(command[-1], "env prompt")
