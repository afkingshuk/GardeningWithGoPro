from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
from pathlib import Path
import threading
import traceback
from typing import Dict
from urllib.parse import parse_qs

from .config_loader import load_config
from .main import build_context, run_encode_upload, run_healthcheck, run_mount_nas, run_sync, run_unmount_nas

logger = logging.getLogger(__name__)


ACTION_LABELS: Dict[str, str] = {
    "sync_wifi": "Sync (Wi-Fi)",
    "sync_sdcard": "Sync (SD Card)",
    "encode_upload": "Encode + Upload",
    "healthcheck": "Healthcheck",
    "mount_nas": "Mount NAS",
    "unmount_nas": "Unmount NAS",
}


@dataclass
class TaskRecord:
    task_id: int
    action: str
    status: str
    started_at: str
    finished_at: str | None = None
    message: str = ""


class DashboardState:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self._lock = threading.Lock()
        self._next_task_id = 1
        self._tasks: list[TaskRecord] = []

    def start(self, action: str) -> int:
        with self._lock:
            task_id = self._next_task_id
            self._next_task_id += 1
            self._tasks.append(
                TaskRecord(
                    task_id=task_id,
                    action=action,
                    status="running",
                    started_at=datetime.now().isoformat(timespec="seconds"),
                )
            )
            self._tasks = self._tasks[-50:]
            return task_id

    def finish(self, task_id: int, status: str, message: str) -> None:
        with self._lock:
            for task in self._tasks:
                if task.task_id == task_id:
                    task.status = status
                    task.finished_at = datetime.now().isoformat(timespec="seconds")
                    task.message = message
                    return

    def list_tasks(self) -> list[TaskRecord]:
        with self._lock:
            return sorted(self._tasks, key=lambda item: item.task_id, reverse=True)


def _execute_action(root_dir: Path, state: DashboardState, task_id: int, action: str) -> None:
    context = None
    try:
        context = build_context(root_dir)
        if action == "sync_wifi":
            run_sync(context, source_override="wifi")
        elif action == "sync_sdcard":
            run_sync(context, source_override="sdcard")
        elif action == "encode_upload":
            run_encode_upload(context)
        elif action == "healthcheck":
            run_healthcheck(context)
        elif action == "mount_nas":
            run_mount_nas(context)
        elif action == "unmount_nas":
            run_unmount_nas(context)
        else:
            raise ValueError(f"Unsupported action: {action}")
        state.finish(task_id, "success", "Completed")
    except Exception as exc:
        logger.exception("Dashboard action failed: %s", action)
        detail = traceback.format_exc(limit=2).strip().splitlines()[-1]
        state.finish(task_id, "error", f"{type(exc).__name__}: {detail}")
    finally:
        if context is not None:
            try:
                context.state_db.close()
            except Exception:
                logger.debug("Failed to close state DB after dashboard action", exc_info=True)


def _render_page(state: DashboardState) -> str:
    config = load_config(state.root_dir)
    sync_source = config.get("sync", {}).get("source", "wifi")
    sdcard_source = config.get("sdcard", {}).get("source_dir", "")
    workspace = config.get("app", {}).get("workspace", "")
    tasks = state.list_tasks()

    actions_html = "\n".join(
        (
            "<form method='post' action='/run'>"
            f"<input type='hidden' name='action' value='{html.escape(action)}'/>"
            f"<button type='submit'>{html.escape(label)}</button>"
            "</form>"
        )
        for action, label in ACTION_LABELS.items()
    )

    rows = []
    for task in tasks:
        label = ACTION_LABELS.get(task.action, task.action)
        rows.append(
            "<tr>"
            f"<td>{task.task_id}</td>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{html.escape(task.status)}</td>"
            f"<td>{html.escape(task.started_at)}</td>"
            f"<td>{html.escape(task.finished_at or '')}</td>"
            f"<td>{html.escape(task.message)}</td>"
            "</tr>"
        )
    tasks_html = "\n".join(rows) if rows else "<tr><td colspan='6'>No tasks yet</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta http-equiv="refresh" content="4"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>GoPro Gardening Dashboard</title>
  <style>
    body {{ font-family: sans-serif; margin: 20px; background: #f3f6fb; color: #10233a; }}
    .card {{ background: white; border-radius: 10px; padding: 14px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    .actions form {{ display: inline-block; margin: 6px 6px 0 0; }}
    button {{ border: 0; border-radius: 8px; padding: 9px 12px; cursor: pointer; background: #165dff; color: #fff; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e5eaf2; padding: 8px; text-align: left; font-size: 13px; }}
    .note {{ font-size: 12px; color: #455a75; }}
    code {{ background: #eef3ff; border-radius: 4px; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>GoPro Gardening Dashboard</h1>
  <div class="card">
    <div><strong>Configured sync source:</strong> <code>{html.escape(str(sync_source))}</code></div>
    <div><strong>SD card source:</strong> <code>{html.escape(str(sdcard_source))}</code></div>
    <div><strong>Workspace:</strong> <code>{html.escape(str(workspace))}</code></div>
    <p class="note">
      USB command/control support depends on camera model and firmware. Original GoPro MAX is typically not
      supported for full Open GoPro USB command-and-control; use Wi-Fi or SD ingest in this dashboard.
    </p>
  </div>

  <div class="card actions">
    <h2>Actions</h2>
    {actions_html}
  </div>

  <div class="card">
    <h2>Task History</h2>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Action</th>
          <th>Status</th>
          <th>Started</th>
          <th>Finished</th>
          <th>Message</th>
        </tr>
      </thead>
      <tbody>
        {tasks_html}
      </tbody>
    </table>
  </div>
</body>
</html>
"""


def serve_ui(root_dir: Path, host: str = "127.0.0.1", port: int = 8787) -> None:
    state = DashboardState(root_dir.resolve())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/":
                self.send_error(404, "Not Found")
                return
            payload = _render_page(state).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/run":
                self.send_error(404, "Not Found")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length).decode("utf-8")
            form = parse_qs(raw)
            action = form.get("action", [""])[0]
            if action not in ACTION_LABELS:
                self.send_error(400, "Unknown action")
                return

            task_id = state.start(action)
            worker = threading.Thread(
                target=_execute_action,
                args=(state.root_dir, state, task_id, action),
                daemon=True,
            )
            worker.start()

            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            logger.info("ui: %s", format % args)

    server = ThreadingHTTPServer((host, port), Handler)
    logger.info("Starting dashboard at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Dashboard interrupted, shutting down")
    finally:
        server.server_close()
