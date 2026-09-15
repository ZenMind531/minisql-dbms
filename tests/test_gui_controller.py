from pathlib import Path
from threading import Event

from database_system.gui.controller import GuiController
from database_system.gui.models import ExecutionBatch


class FakeService:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.closed = False

    def execute(self, sql: str) -> ExecutionBatch:
        return ExecutionBatch()

    def schema_snapshot(self):
        return ()

    def close(self) -> None:
        self.closed = True


def test_controller_executes_and_delivers_response(tmp_path: Path) -> None:
    controller = GuiController(tmp_path, service_factory=FakeService)
    try:
        assert controller.execute("SHOW TABLES;") is True
        response = controller.wait_for_response(timeout=1)
        assert response.kind == "execute"
        assert isinstance(response.payload, ExecutionBatch)
        assert controller.busy is False
    finally:
        controller.close()


def test_controller_switches_directory_and_closes_old_service(tmp_path: Path) -> None:
    made: list[FakeService] = []

    def factory(path):
        service = FakeService(path)
        made.append(service)
        return service

    controller = GuiController(tmp_path / "one", service_factory=factory)
    try:
        assert controller.open_directory(tmp_path / "two") is True
        response = controller.wait_for_response(timeout=1)
        assert response.kind == "open"
        assert made[0].closed is True
        assert made[1].data_dir == tmp_path / "two"
    finally:
        controller.close()
