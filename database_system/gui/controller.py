from __future__ import annotations

from pathlib import Path
from queue import Empty
from typing import Any, Callable

from database_system.gui.service import DatabaseService
from database_system.gui.worker import DatabaseWorker, WorkerResponse


class GuiController:
    def __init__(self, data_dir: str | Path = "data/", *,
                 service_factory: Callable[[str | Path], Any] = DatabaseService) -> None:
        self.worker = DatabaseWorker(data_dir, service_factory)
        self.busy = False

    def execute(self, sql: str) -> bool:
        return self._submit("execute", sql)

    def refresh_schema(self) -> bool:
        return self._submit("schema")

    def open_directory(self, path: str | Path) -> bool:
        return self._submit("open", Path(path))

    def poll_response(self) -> WorkerResponse | None:
        try:
            response = self.worker.responses.get_nowait()
        except Empty:
            return None
        self.busy = False
        return response

    def wait_for_response(self, timeout: float = 5) -> WorkerResponse:
        response = self.worker.responses.get(timeout=timeout)
        self.busy = False
        return response

    def close(self) -> None:
        self.worker.close()
        self.busy = False

    def _submit(self, kind: str, payload: Any = None) -> bool:
        if self.busy:
            return False
        self.busy = True
        self.worker.submit(kind, payload)
        return True

