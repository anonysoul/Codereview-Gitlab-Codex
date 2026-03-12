import os
import shutil
import subprocess

from biz.utils.log import logger


DEFAULT_CODEX_REVIEW_PROMPT = (
    "请用中文输出适合直接回复到 GitLab Merge Request 的审查结论。"
    "聚焦 bug、风险、回归和缺失测试。"
    "如果没有发现明确问题，直接说明未发现阻塞性问题，并提示仍需人工确认边界场景。"
)


class CodexReviewRunner:
    def __init__(self, prompt: str | None = None):
        self.prompt = prompt or os.getenv("CODEX_REVIEW_PROMPT", DEFAULT_CODEX_REVIEW_PROMPT)

    def review(self, repo_path: str, base_ref: str) -> str:
        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("`codex` executable not found in PATH.")

        command = [codex_path, "review", "--base", base_ref, self.prompt]
        logger.info("Running Codex review in %s against %s", repo_path, base_ref)
        result = subprocess.run(
            command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Codex review failed with exit code {result.returncode}: {result.stderr.strip()}"
            )

        review_result = result.stdout.strip()
        if not review_result:
            raise RuntimeError("Codex review returned empty output.")

        return review_result
