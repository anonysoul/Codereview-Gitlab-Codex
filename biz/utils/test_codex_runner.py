import os
import subprocess
from unittest import TestCase
from unittest.mock import patch

from biz.utils.codex_runner import CodexReviewRunner


class TestCodexReviewRunner(TestCase):
    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    def test_review_returns_stdout(self, mock_run, _mock_which):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout="review result\n",
            stderr="",
        )

        result = CodexReviewRunner(prompt="custom prompt").review("/tmp/repo", "origin/main")

        self.assertEqual(result, "review result")
        mock_run.assert_called_once()

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    def test_review_raises_when_codex_fails(self, mock_run, _mock_which):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=1,
            stdout="",
            stderr="boom",
        )

        with self.assertRaisesRegex(RuntimeError, "Codex review failed"):
            CodexReviewRunner().review("/tmp/repo", "origin/main")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    def test_review_raises_when_output_is_empty(self, mock_run, _mock_which):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout=" \n",
            stderr="",
        )

        with self.assertRaisesRegex(RuntimeError, "empty output"):
            CodexReviewRunner().review("/tmp/repo", "origin/main")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    def test_review_uses_env_prompt_when_present(self, mock_run, _mock_which):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        with patch.dict(os.environ, {"CODEX_REVIEW_PROMPT": "env prompt"}, clear=False):
            CodexReviewRunner().review("/tmp/repo", "origin/main")

        command = mock_run.call_args.args[0]
        self.assertEqual(command[-1], "env prompt")
