import os
from io import StringIO
from unittest import TestCase
from unittest.mock import MagicMock, patch

from biz.utils.codex_runner import CodexReviewRunner, DEFAULT_EMPTY_REVIEW_RESULT


class TestCodexReviewRunner(TestCase):
    def test_protect_translation_literals_preserves_structured_tokens(self):
        review_text = (
            "[P1] Correct the step name — /tmp/repo/bdd/features/flow/BDD-FLOWSEC-0004.yml:40-40 "
            "The new case interpolates WORKFLOW_ID from `创建外部提交审批单并上传附件`, "
            "and uses PUT /api/v2/workflows/{id}/extra-props."
        )

        protected, replacements = CodexReviewRunner._protect_translation_literals(review_text)
        restored = CodexReviewRunner._restore_translation_literals(protected, replacements)

        self.assertIn("[[codex_literal_", protected)
        self.assertEqual(restored, review_text)

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.logger")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_returns_stdout(self, mock_popen, mock_logger, mock_run, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("review result\n")
        process.stderr = StringIO("progress line\n")
        process.wait.return_value = 0
        mock_popen.return_value = process
        mock_run.return_value = MagicMock(returncode=0, stdout="中文审查结果", stderr="")

        result = CodexReviewRunner(prompt="custom prompt").review("/tmp/repo", "origin/main")

        self.assertEqual(result, "中文审查结果")
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
    @patch("biz.utils.codex_runner.logger")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_returns_fallback_when_output_is_empty(self, mock_popen, mock_run, mock_logger, _mock_which):
        process = MagicMock()
        process.stdout = StringIO(" \n")
        process.stderr = StringIO("")
        process.wait.return_value = 0
        mock_popen.return_value = process
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = CodexReviewRunner().review("/tmp/repo", "origin/main")

        self.assertEqual(result, DEFAULT_EMPTY_REVIEW_RESULT)
        mock_logger.warning.assert_any_call(
            "Codex review returned empty output, using fallback summary."
        )

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_uses_review_comment_from_stderr_when_stdout_is_empty(self, mock_popen, mock_run, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("")
        process.stderr = StringIO(
            "Review comment:\n"
            "- [P1] Fix migration\n"
            "  This migration fails.\n"
        )
        process.wait.return_value = 0
        mock_popen.return_value = process
        mock_run.return_value = MagicMock(returncode=0, stdout="- [P1] 修复迁移\n  该迁移会失败。", stderr="")

        result = CodexReviewRunner().review("/tmp/repo", "origin/main")

        self.assertEqual(
            result,
            "- [P1] 修复迁移\n  该迁移会失败。"
        )

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_prefers_full_review_comments_section(self, mock_popen, mock_run, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("")
        process.stderr = StringIO(
            "OpenAI Codex v0.114.0\n"
            "some execution logs\n"
            "Full review comments:\n\n"
            "[P1] Fix login flow\n"
            "Detailed explanation.\n"
        )
        process.wait.return_value = 0
        mock_popen.return_value = process
        mock_run.return_value = MagicMock(returncode=0, stdout="[P1] 修复登录流程\n详细说明。", stderr="")

        result = CodexReviewRunner().review("/tmp/repo", "origin/main")

        self.assertEqual(result, "[P1] 修复登录流程\n详细说明。")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_uses_env_prompt_when_present(self, mock_popen, mock_run, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("ok")
        process.stderr = StringIO("")
        process.wait.return_value = 0
        mock_popen.return_value = process
        mock_run.return_value = MagicMock(returncode=0, stdout="中文结果", stderr="")

        with patch.dict(os.environ, {"CODEX_REVIEW_PROMPT": "env prompt"}, clear=False):
            CodexReviewRunner().review("/tmp/repo", "origin/main")

        command = mock_popen.call_args.args[0]
        self.assertEqual(command[-1], "env prompt")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.logger")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_retries_without_prompt_when_codex_cli_rejects_prompt(
        self,
        mock_popen,
        mock_run,
        mock_logger,
        _mock_which,
    ):
        first_process = MagicMock()
        first_process.stdout = StringIO("")
        first_process.stderr = StringIO(
            "error: the argument '--base <BRANCH>' cannot be used with '[PROMPT]'\n"
        )
        first_process.wait.return_value = 2

        second_process = MagicMock()
        second_process.stdout = StringIO("review result\n")
        second_process.stderr = StringIO("")
        second_process.wait.return_value = 0

        mock_popen.side_effect = [first_process, second_process]
        mock_run.return_value = MagicMock(returncode=0, stdout="中文审查结果", stderr="")

        result = CodexReviewRunner(prompt="custom prompt").review("/tmp/repo", "origin/main")

        self.assertEqual(result, "中文审查结果")
        self.assertEqual(mock_popen.call_count, 2)
        self.assertEqual(
            mock_popen.call_args_list[0].args[0],
            ["/usr/bin/codex", "review", "--base", "origin/main", "custom prompt"],
        )
        self.assertEqual(
            mock_popen.call_args_list[1].args[0],
            ["/usr/bin/codex", "review", "--base", "origin/main"],
        )
        mock_logger.warning.assert_any_call(
            "Codex CLI rejected review prompt with --base, retrying without custom prompt."
        )

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_keeps_original_text_when_translation_fails(self, mock_popen, mock_run, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("review result\n")
        process.stderr = StringIO("")
        process.wait.return_value = 0
        mock_popen.return_value = process
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="translate failed")

        result = CodexReviewRunner().review("/tmp/repo", "origin/main")

        self.assertEqual(result, "review result")

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_skips_translation_when_output_is_already_chinese(self, mock_popen, mock_run, _mock_which):
        process = MagicMock()
        process.stdout = StringIO("这是中文审查结果\n")
        process.stderr = StringIO("")
        process.wait.return_value = 0
        mock_popen.return_value = process

        result = CodexReviewRunner().review("/tmp/repo", "origin/main")

        self.assertEqual(result, "这是中文审查结果")
        mock_run.assert_not_called()

    @patch("biz.utils.codex_runner.shutil.which", return_value="/usr/bin/codex")
    @patch("biz.utils.codex_runner.subprocess.run")
    @patch("biz.utils.codex_runner.subprocess.Popen")
    def test_review_restores_protected_literals_after_translation(self, mock_popen, mock_run, _mock_which):
        original_review = (
            "[P2] Update WF-FLOWSEC-001 to match the new extra-props verb — "
            "/tmp/repo/spec/workflows/flow/WF-FLOWSEC-001.md:37-37 "
            "BDD-FLOWSEC-0001 now exercises PUT /api/v2/workflows/{id}/extra-props.\n"
        )
        protected, replacements = CodexReviewRunner._protect_translation_literals(original_review.strip())

        process = MagicMock()
        process.stdout = StringIO(original_review)
        process.stderr = StringIO("")
        process.wait.return_value = 0
        mock_popen.return_value = process
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                protected
                .replace("Update ", "更新")
                .replace(" to match the new extra-props verb", " 以匹配新的 extra-props 动词")
                .replace(" now exercises ", " 现在使用 ")
            ),
            stderr="",
        )

        result = CodexReviewRunner().review("/tmp/repo", "origin/main")

        self.assertIn("WF-FLOWSEC-001", result)
        self.assertIn("/tmp/repo/spec/workflows/flow/WF-FLOWSEC-001.md:37-37", result)
        self.assertIn("BDD-FLOWSEC-0001", result)
        self.assertIn("PUT", result)
        self.assertIn("/api/v2/workflows/{id}/extra-props", result)
