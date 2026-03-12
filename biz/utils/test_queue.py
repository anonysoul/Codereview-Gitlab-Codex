import os
import tempfile
import time
from multiprocessing import Event, Process
from unittest import TestCase
from unittest.mock import MagicMock, patch

from biz.utils.queue import (
    _queue_lock,
    _run_task,
    build_merge_request_task_key,
    build_repository_queue_key,
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

    def test_build_repository_queue_key(self):
        queue_key = build_repository_queue_key(
            {
                "project": {"id": 123},
                "object_attributes": {"iid": 9},
            },
            "gitlab_example",
        )

        self.assertEqual(queue_key, "gitlab_example__project_123")

    def test_run_task_executes_function_under_queue_lock(self):
        function = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CODEREVIEW_TASK_REGISTRY_DIR": tmpdir}, clear=False):
                _run_task(function, {}, "token", "url", "slug", "repo-1")

        function.assert_called_once_with({}, "token", "url", "slug")

    def test_handle_queue_starts_process_with_queue_key(self):
        process = MagicMock()
        process.pid = 4321

        with patch("biz.utils.queue.Process", return_value=process):
            handle_queue(lambda *_args: None, {}, "token", "url", "slug", queue_key="repo-1")

        process.start.assert_called_once()

    def test_queue_lock_blocks_later_task_until_previous_finishes(self):
        entered_second_lock = Event()
        release_first_lock = Event()

        def hold_first_lock(tmpdir: str):
            os.environ["CODEREVIEW_TASK_REGISTRY_DIR"] = tmpdir
            with _queue_lock("repo-1"):
                release_first_lock.wait(timeout=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            def enter_second_lock():
                os.environ["CODEREVIEW_TASK_REGISTRY_DIR"] = tmpdir
                with _queue_lock("repo-1"):
                    entered_second_lock.set()

            holder = Process(target=hold_first_lock, args=(tmpdir,))
            holder.start()
            time.sleep(0.2)

            waiter = Process(target=enter_second_lock)
            waiter.start()
            time.sleep(0.2)
            self.assertFalse(entered_second_lock.is_set())

            release_first_lock.set()
            waiter.join(timeout=2)
            holder.join(timeout=2)

        self.assertTrue(entered_second_lock.is_set())
