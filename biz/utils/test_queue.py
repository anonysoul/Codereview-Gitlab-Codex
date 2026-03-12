import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from biz.utils.queue import (
    _run_task,
    _terminate_previous_task,
    _write_task_state,
    build_merge_request_task_key,
    handle_queue,
)


class TestQueue(TestCase):
    def test_build_merge_request_task_key(self):
        task_key = build_merge_request_task_key(
            {
                "project": {"id": 123},
                "object_attributes": {"iid": 9},
            },
            "gitlab_example",
        )

        self.assertEqual(task_key, "gitlab_example__project_123__mr_9")

    def test_run_task_skips_stale_run(self):
        function = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CODEREVIEW_TASK_REGISTRY_DIR": tmpdir}, clear=False):
                _write_task_state("task", {"pid": 1, "run_id": "new"})
                _run_task(function, {}, "token", "url", "slug", "task", "old")

        function.assert_not_called()

    def test_handle_queue_cancels_previous_task_and_starts_new_one(self):
        process = MagicMock()
        process.pid = 4321

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CODEREVIEW_TASK_REGISTRY_DIR": tmpdir}, clear=False):
                _write_task_state("task", {"pid": 1234, "run_id": "old"})
                with patch("biz.utils.queue.Process", return_value=process):
                    with patch("biz.utils.queue.os.killpg") as killpg:
                        handle_queue(lambda *_args: None, {}, "token", "url", "slug", task_key="task")

                killpg.assert_called_once()
                process.start.assert_called_once()
                state_path = Path(tmpdir) / "task.json"
                self.assertTrue(state_path.exists())
                self.assertIn('"pid": 4321', state_path.read_text(encoding="utf-8"))

    def test_terminate_previous_task_ignores_missing_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CODEREVIEW_TASK_REGISTRY_DIR": tmpdir}, clear=False):
                _write_task_state("task", {"pid": 9999, "run_id": "old"})
                with patch("biz.utils.queue.os.killpg", side_effect=ProcessLookupError):
                    _terminate_previous_task("task")
