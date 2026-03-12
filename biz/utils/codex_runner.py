import os
import shutil
import subprocess
import threading

from biz.utils.log import logger


DEFAULT_CODEX_REVIEW_PROMPT = (
    "请用中文输出适合直接回复到 GitLab Merge Request 的审查结论。"
    "聚焦 bug、风险、回归和缺失测试。"
    "如果没有发现明确问题，直接说明未发现阻塞性问题，并提示仍需人工确认边界场景。"
)

DEFAULT_EMPTY_REVIEW_RESULT = (
    "未发现阻塞性问题。\n"
    "Codex 本次未返回详细审查内容，请人工复核关键边界场景、回归影响和测试覆盖。"
)


class CodexReviewRunner:
    def __init__(self, prompt: str | None = None):
        self.prompt = prompt or os.getenv("CODEX_REVIEW_PROMPT", DEFAULT_CODEX_REVIEW_PROMPT)

    @staticmethod
    def _stream_pipe(pipe, chunks: list[str], log_method) -> None:
        if pipe is None:
            return

        try:
            for line in iter(pipe.readline, ""):
                chunks.append(line)
                message = line.rstrip()
                if message:
                    log_method("codex review: %s", message)
        finally:
            pipe.close()

    def review(self, repo_path: str, base_ref: str) -> str:
        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("`codex` executable not found in PATH.")

        command = [codex_path, "review", "--base", base_ref, self.prompt]
        try:
            return self._run_review_command(command, repo_path, base_ref)
        except RuntimeError as exc:
            if self._should_retry_without_prompt(exc):
                retry_command = [codex_path, "review", "--base", base_ref]
                logger.warning(
                    "Codex CLI rejected review prompt with --base, retrying without custom prompt."
                )
                return self._run_review_command(retry_command, repo_path, base_ref)
            raise

    def _run_review_command(self, command: list[str], repo_path: str, base_ref: str) -> str:
        logger.info("Running Codex review in %s against %s", repo_path, base_ref)
        process = subprocess.Popen(
            command,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        stderr_thread = threading.Thread(
            target=self._stream_pipe,
            args=(process.stderr, stderr_chunks, logger.warning),
            daemon=True,
        )
        stderr_thread.start()

        self._stream_pipe(process.stdout, stdout_chunks, logger.info)
        return_code = process.wait()
        stderr_thread.join()

        if return_code != 0:
            error_output = "".join(stderr_chunks).strip() or "".join(stdout_chunks).strip()
            raise RuntimeError(
                f"Codex review failed with exit code {return_code}: {error_output}"
            )

        review_result = self._extract_review_result(stdout_chunks, stderr_chunks)
        if not review_result:
            logger.warning("Codex review returned empty output, using fallback summary.")
            return DEFAULT_EMPTY_REVIEW_RESULT

        return review_result

    @staticmethod
    def _should_retry_without_prompt(exc: RuntimeError) -> bool:
        message = str(exc)
        return (
            "the argument '--base <BRANCH>' cannot be used with '[PROMPT]'" in message
            or "cannot be used with '[PROMPT]'" in message
        )

    @staticmethod
    def _extract_review_result(stdout_chunks: list[str], stderr_chunks: list[str]) -> str:
        stdout_text = "".join(stdout_chunks).strip()
        if stdout_text:
            return stdout_text

        stderr_text = "".join(stderr_chunks).strip()
        if not stderr_text:
            return ""

        marker = "Review comment:"
        marker_index = stderr_text.find(marker)
        if marker_index >= 0:
            comment = stderr_text[marker_index + len(marker):].strip()
            if comment:
                return comment

        return stderr_text
