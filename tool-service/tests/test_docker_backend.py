"""Docker runtime backend tests."""

import pytest
from docker.errors import DockerException, NotFound

from seedemu_tool_service.backends.docker import (
    DockerRuntimeBackend,
    RuntimeBackendError,
    RuntimeTargetNotFoundError,
)


class AvailableDockerClient:
    def ping(self) -> bool:
        return True

    def version(self) -> dict[str, str]:
        return {"Version": "test-version"}


class UnavailableDockerClient:
    def ping(self) -> bool:
        raise DockerException("daemon unavailable")


class CommandContainer:
    def __init__(self) -> None:
        self.command: list[str] | None = None
        self.demux: bool | None = None

    def exec_run(
        self,
        command: list[str],
        *,
        demux: bool,
    ) -> tuple[int, tuple[bytes, bytes]]:
        self.command = command
        self.demux = demux
        return 0, (b"standard output\n", b"standard error\n")


class ContainerCollection:
    def __init__(self, container: CommandContainer) -> None:
        self.container = container
        self.requested_name: str | None = None

    def get(self, name: str) -> CommandContainer:
        self.requested_name = name
        return self.container


class CommandDockerClient:
    def __init__(self, container: CommandContainer) -> None:
        self.containers = ContainerCollection(container)


class MissingContainerCollection:
    def get(self, name: str) -> None:
        raise NotFound(f"No such container: {name}")


class MissingContainerDockerClient:
    def __init__(self) -> None:
        self.containers = MissingContainerCollection()


class FailingContainerCollection:
    def get(self, name: str) -> None:
        raise DockerException("daemon unavailable")


class FailingCommandDockerClient:
    def __init__(self) -> None:
        self.containers = FailingContainerCollection()


def test_docker_backend_reports_daemon_version() -> None:
    backend = DockerRuntimeBackend(client=AvailableDockerClient())

    assert backend.status().model_dump() == {
        "backend": "docker",
        "available": True,
        "daemon_version": "test-version",
    }


def test_docker_backend_reports_unavailable_daemon() -> None:
    backend = DockerRuntimeBackend(client=UnavailableDockerClient())

    assert backend.status().model_dump() == {
        "backend": "docker",
        "available": False,
        "daemon_version": None,
    }


def test_docker_backend_handles_client_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_client() -> None:
        raise DockerException("socket unavailable")

    monkeypatch.setattr("seedemu_tool_service.backends.docker.docker.from_env", unavailable_client)

    assert DockerRuntimeBackend().status().available is False


def test_docker_backend_executes_argument_vector_in_container() -> None:
    container = CommandContainer()
    client = CommandDockerClient(container)
    backend = DockerRuntimeBackend(client=client)

    result = backend.execute("source-node", ["ping", "-c", "1", "10.0.0.1"])

    assert client.containers.requested_name == "source-node"
    assert container.command == ["ping", "-c", "1", "10.0.0.1"]
    assert container.demux is True
    assert result.model_dump() == {
        "exit_code": 0,
        "stdout": "standard output\n",
        "stderr": "standard error\n",
    }


def test_docker_backend_reports_missing_target() -> None:
    backend = DockerRuntimeBackend(client=MissingContainerDockerClient())

    with pytest.raises(
        RuntimeTargetNotFoundError,
        match="Emulated node not found: missing-node",
    ):
        backend.execute("missing-node", ["ping", "127.0.0.1"])


def test_docker_backend_wraps_docker_failure() -> None:
    backend = DockerRuntimeBackend(client=FailingCommandDockerClient())

    with pytest.raises(RuntimeBackendError, match="Docker command execution failed"):
        backend.execute("source-node", ["ping", "127.0.0.1"])
