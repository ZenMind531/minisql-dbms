from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, Callable

from database_system.gui.service import DatabaseService


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    kind: str
    payload: Any = None


@dataclass(frozen=True, slots=True)
class WorkerResponse:
    kind: str
    payload: Any = None
    error: Exception | None = None


class DatabaseWorker:
    def __init__(self, data_dir: str | Path,
                 service_factory: Callable[[str | Path], Any] = DatabaseService) -> None:
        self.requests: Queue[WorkerRequest] = Queue()
        self.responses: Queue[WorkerResponse] = Queue()
        self._initial_dir = Path(data_dir)
        self._factory = service_factory
        self._thread = Thread(target=self._run, name="MiniSQL-GUI", daemon=True)
        self._thread.start()

    def submit(self, kind: str, payload: Any = None) -> None:
        self.requests.put(WorkerRequest(kind, payload))

    def close(self) -> None:
        self.submit("close")
        self._thread.join(timeout=5)

    def _run(self) -> None:
        service = self._factory(self._initial_dir)
        while True:
            request = self.requests.get()
            try:
                if request.kind == "close":
                    service.close()
                    return
                if request.kind == "execute":
                    payload = service.execute(request.payload)
                elif request.kind == "schema":
                    payload = service.schema_snapshot()
                elif request.kind == "open":
                    new_service = self._factory(request.payload)
                    old_service = service
                    service = new_service
                    old_service.close()
                    payload = service.schema_snapshot()
                else:
                    raise ValueError(f"unknown worker request: {request.kind}")
                self.responses.put(WorkerResponse(request.kind, payload))
            except Exception as exc:
                self.responses.put(WorkerResponse(request.kind, error=exc))

