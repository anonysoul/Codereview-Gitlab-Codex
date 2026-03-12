import fcntl
import os
import tempfile
from contextlib import contextmanager
from multiprocessing import Process
from pathlib import Path

from biz.utils.log import logger


DEFAULT_TASK_REGISTRY_DIR = Path(tempfile.gettempdir()) / "codereview-task-registry"


def _extract_project_id(webhook_data: dict) -> str | int:
    object_attributes = webhook_data.get("object_attributes", {})
    project = webhook_data.get("project", {})
    project_id = (
        project.get("id")
        or object_attributes.get("target_project_id")
        or object_attributes.get("source_project_id")
    )
    if not project_id:
        raise ValueError("Missing project id for queue task key.")
    return project_id


def build_merge_request_task_key(webhook_data: dict, url_slug: str) -> str:
    object_attributes = webhook_data.get("object_attributes", {})
    project_id = _extract_project_id(webhook_data)
    mr_iid = object_attributes.get("iid")
    if not project_id or not mr_iid:
        raise ValueError("Missing project id or merge request iid for queue task key.")
    return f"{url_slug}__project_{project_id}__mr_{mr_iid}"


def build_repository_queue_key(webhook_data: dict, url_slug: str) -> str:
    project_id = _extract_project_id(webhook_data)
    return f"{url_slug}__project_{project_id}"


def handle_queue(
    function: callable,
    data: any,
    token: str,
    url: str,
    url_slug: str,
    queue_key: str | None = None,
):
    process = Process(
        target=_run_task,
        args=(function, data, token, url, url_slug, queue_key),
    )
    process.start()
    if queue_key:
        logger.info("Queued review task: queue_key=%s pid=%s", queue_key, process.pid)


def _run_task(
    function: callable,
    data: any,
    token: str,
    url: str,
    url_slug: str,
    queue_key: str | None,
):
    if hasattr(os, "setsid"):
        try:
            os.setsid()
        except OSError:
            logger.warning("Failed to create a dedicated process group for queue_key=%s", queue_key)

    with _queue_lock(queue_key):
        function(data, token, url, url_slug)


def _task_registry_dir() -> Path:
    registry_dir = Path(os.getenv("CODEREVIEW_TASK_REGISTRY_DIR", str(DEFAULT_TASK_REGISTRY_DIR)))
    registry_dir.mkdir(parents=True, exist_ok=True)
    return registry_dir


def _queue_lock_path(queue_key: str) -> Path:
    return _task_registry_dir() / f"{queue_key}.lock"


@contextmanager
def _queue_lock(queue_key: str | None):
    if not queue_key:
        yield
        return

    lock_path = _queue_lock_path(queue_key)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        logger.info("Waiting for repository review slot: queue_key=%s", queue_key)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        logger.info("Acquired repository review slot: queue_key=%s", queue_key)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            logger.info("Released repository review slot: queue_key=%s", queue_key)
