import json
import os
import signal
import tempfile
import time
from multiprocessing import Process
from pathlib import Path

from biz.utils.log import logger


DEFAULT_TASK_REGISTRY_DIR = Path(tempfile.gettempdir()) / "codereview-task-registry"


def build_merge_request_task_key(webhook_data: dict, url_slug: str) -> str:
    object_attributes = webhook_data.get("object_attributes", {})
    project = webhook_data.get("project", {})
    project_id = (
        project.get("id")
        or object_attributes.get("target_project_id")
        or object_attributes.get("source_project_id")
    )
    mr_iid = object_attributes.get("iid")
    if not project_id or not mr_iid:
        raise ValueError("Missing project id or merge request iid for queue task key.")
    return f"{url_slug}__project_{project_id}__mr_{mr_iid}"


def handle_queue(
    function: callable,
    data: any,
    token: str,
    url: str,
    url_slug: str,
    task_key: str | None = None,
):
    run_id = str(time.time_ns()) if task_key else None
    if task_key:
        _terminate_previous_task(task_key)

    process = Process(
        target=_run_task,
        args=(function, data, token, url, url_slug, task_key, run_id),
    )
    process.start()
    if task_key:
        _write_task_state(task_key, {"pid": process.pid, "run_id": run_id})
        logger.info("Queued latest MR review task: task_key=%s pid=%s run_id=%s", task_key, process.pid, run_id)


def _run_task(
    function: callable,
    data: any,
    token: str,
    url: str,
    url_slug: str,
    task_key: str | None,
    run_id: str | None,
):
    if hasattr(os, "setsid"):
        try:
            os.setsid()
        except OSError:
            logger.warning("Failed to create a dedicated process group for task_key=%s", task_key)

    if task_key and run_id and not _wait_until_task_is_current(task_key, run_id):
        logger.info("Skipping stale queued MR review task: task_key=%s run_id=%s", task_key, run_id)
        return

    try:
        function(data, token, url, url_slug)
    finally:
        if task_key and run_id:
            _clear_task_state_if_current(task_key, run_id)


def _task_registry_dir() -> Path:
    registry_dir = Path(os.getenv("CODEREVIEW_TASK_REGISTRY_DIR", str(DEFAULT_TASK_REGISTRY_DIR)))
    registry_dir.mkdir(parents=True, exist_ok=True)
    return registry_dir


def _task_state_path(task_key: str) -> Path:
    return _task_registry_dir() / f"{task_key}.json"


def _read_task_state(task_key: str) -> dict | None:
    path = _task_state_path(task_key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_task_state(task_key: str, state: dict):
    path = _task_state_path(task_key)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp_path, path)


def _clear_task_state_if_current(task_key: str, run_id: str):
    state = _read_task_state(task_key)
    if state and state.get("run_id") == run_id:
        try:
            _task_state_path(task_key).unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove task registry for task_key=%s", task_key)


def _wait_until_task_is_current(task_key: str, run_id: str, timeout_seconds: float = 3.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        state = _read_task_state(task_key)
        if state and state.get("run_id") == run_id:
            return True
        if state and state.get("run_id") != run_id:
            return False
        time.sleep(0.05)
    return False


def _terminate_previous_task(task_key: str):
    state = _read_task_state(task_key)
    if not state:
        return

    pid = state.get("pid")
    if not pid:
        return

    try:
        if hasattr(os, "killpg"):
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
        logger.info("Cancelled previous MR review task: task_key=%s pid=%s", task_key, pid)
    except ProcessLookupError:
        logger.info("Previous MR review task already exited: task_key=%s pid=%s", task_key, pid)
    except OSError as exc:
        logger.warning("Failed to cancel previous MR review task: task_key=%s pid=%s error=%s", task_key, pid, exc)
