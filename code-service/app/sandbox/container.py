"""Sandbox container lifecycle via the Docker SDK (build plan Step 2).

Docker-outside-of-Docker: code-service talks to the host daemon over the
mounted /var/run/docker.sock. One ephemeral sandbox container per AgentRun,
living for the run's full duration and torn down on terminal success/failure.

Dangerous-action mount boundary (Step 12): ONLY the working repo directory is
bind-mounted into the container. Nothing else on the host is reachable,
regardless of what the agent attempts — a stronger guarantee than an
event-stream interceptor because a mount boundary can't be reasoned around.

Step 4 addition: the sandbox image now runs an OpenHands Agent Server
(baked into sandbox/Dockerfile, Step 1). Its port is published to a
Docker-assigned free host port (never hardcoded — concurrent AgentRuns must
not collide) and carried on SandboxHandle for the controller to connect to
via RemoteWorkspace.
"""

import logging
import re
import socket
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

from app.config import (
    AGENT_SERVER_HOST,
    AGENT_SERVER_INTERNAL_PORT,
    SANDBOX_IMAGE,
    SANDBOX_REPO_MOUNT,
)
from app.sandbox.resources import ResourceTier, resolve_allocation

logger = logging.getLogger(__name__)

_AGENT_SERVER_CONTAINER_PORT = f"{AGENT_SERVER_INTERNAL_PORT}/tcp"


class SandboxError(RuntimeError):
    """Any failure creating/operating the sandbox — a Hard Technical failure."""


@dataclass
class SandboxHandle:
    container_id: str
    name: str
    repo_mount: str
    tier_name: str
    agent_server_port: int  # host-side port published for the agent server
    _container: Any  # docker.models.containers.Container
    agent_server_host: str = "host.docker.internal"  # Added to resolve direct sibling routing


def _client() -> "docker.DockerClient":
    try:
        return docker.from_env()
    except DockerException as exc:  # pragma: no cover - env dependent
        raise SandboxError(f"Could not connect to Docker daemon: {exc}") from exc


def sandbox_name(agent_run_id: str) -> str:
    return f"synapse-sandbox-{agent_run_id}"


def _find_current_container(client: docker.DockerClient) -> Any:
    """Finds the current running container by ID, hostname, or name matching."""
    # Try 1: By reading /proc/self/cgroup to get the 64-char container ID
    for filepath in ("/proc/self/cgroup", "/proc/1/cpuset"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r"([a-f0-9]{64})", content)
                if match:
                    container_id = match.group(1)
                    return client.containers.get(container_id)
        except Exception:
            pass

    # Try 2: By using socket.gethostname() directly
    try:
        hostname = socket.gethostname()
        return client.containers.get(hostname)
    except Exception:
        pass

    # Try 3: List all containers and find the one that matches our hostname or name pattern
    try:
        hostname = socket.gethostname()
        for container in client.containers.list():
            # Check ID matching
            if container.id.startswith(hostname) or hostname.startswith(container.id[:12]):
                return container
            # Check Name matching
            name = container.name.lstrip("/")
            if name == hostname or name == "synapse-code-service" or "code-service" in name:
                return container
    except Exception:
        pass

    return None


def create_sandbox(agent_run_id: str, host_repo_path: str) -> SandboxHandle:
    """Create + start one sandbox container bound to the run's repo directory.

    host_repo_path is a path on the HOST that the daemon can bind-mount (the
    controller and the daemon share the REPO_WORK_ROOT volume). It is mounted
    read-write at SANDBOX_REPO_MOUNT and is the only host path visible inside.
    """
    client = _client()
    tier: ResourceTier = resolve_allocation(host_repo_path)
    name = sandbox_name(agent_run_id)

    # Idempotency: if a stale container with this name survives (e.g. crash
    # before teardown), remove it before recreating.
    try:
        existing = client.containers.get(name)
        logger.warning("Removing stale sandbox container %s", name)
        existing.remove(force=True)
    except NotFound:
        pass
    except APIError as exc:  # pragma: no cover
        logger.warning("Could not inspect/remove stale container %s: %s", name, exc)

    # Dynamic sibling container network detection
    network_name = "bridge"
    is_sibling = False
    try:
        current_container = _find_current_container(client)
        if current_container:
            networks = current_container.attrs.get("NetworkSettings", {}).get("Networks", {})
            if networks:
                # Look for a custom user network rather than the default 'bridge'
                network_candidates = [n for n in networks.keys() if n != "bridge"]
                if network_candidates:
                    network_name = network_candidates[0]
                    is_sibling = True
                else:
                    network_name = list(networks.keys())[0]
                logger.info("Detected sibling container network: %s. Using sibling container routing.", network_name)
            else:
                logger.info("No networks found on current container. Defaulting to host loopback/bridge routing.")
        else:
            logger.info("Could not resolve current container object from Docker. Defaulting to host loopback/bridge routing.")
    except Exception as exc:
        logger.warning("Failed to detect sibling network; falling back to host mode: %s", exc, exc_info=True)

    try:
        container = client.containers.run(
            image=SANDBOX_IMAGE,
            name=name,
            detach=True,
            # Mount boundary: only the repo dir, nothing else.
            volumes={host_repo_path: {"bind": SANDBOX_REPO_MOUNT, "mode": "rw"}},
            working_dir=SANDBOX_REPO_MOUNT,
            # Publish the agent-server port to a Docker-assigned free host
            # port (None => random). Never fix this to a single host port:
            # multiple concurrent AgentRuns each need their own.
            ports={_AGENT_SERVER_CONTAINER_PORT: None},
            # Resource ceiling (Docker limits, mirroring k8s limits).
            nano_cpus=int(tier.cpus * 1_000_000_000),
            mem_limit=tier.mem_bytes,
            # Assign network dynamically
            network_mode=network_name,
            # Drop privileges; the agent never needs root capabilities.
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            auto_remove=False,
        )
    except ImageNotFound as exc:
        raise SandboxError(
            f"Sandbox image {SANDBOX_IMAGE!r} not found. Build it: "
            f"docker build -t {SANDBOX_IMAGE} code-service/sandbox"
        ) from exc
    except (APIError, DockerException) as exc:
        raise SandboxError(f"Failed to start sandbox container: {exc}") from exc

    # Resolve direct routing host and port for the handle
    if is_sibling:
        container.reload()
        networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        sibling_net = networks.get(network_name, {})
        ip_address = sibling_net.get("IPAddress")
        if ip_address:
            agent_server_host = ip_address  # Bypasses DNS lookup delay completely
        else:
            agent_server_host = name  # Fallback to name if IP is not yet populated
        agent_server_port = AGENT_SERVER_INTERNAL_PORT
    else:
        agent_server_host = AGENT_SERVER_HOST  # Non-sibling connects via "host.docker.internal"
        agent_server_port = _discover_published_port(container, name)

    logger.info(
        "Started sandbox %s (id=%s, tier=%s, %.2f CPU / %d MB, agent-server port %d, host %s)",
        name,
        container.id[:12],
        tier.name,
        tier.cpus,
        tier.mem_bytes // 1024**2,
        agent_server_port,
        agent_server_host,
    )
    return SandboxHandle(
        container_id=container.id,
        name=name,
        repo_mount=SANDBOX_REPO_MOUNT,
        tier_name=tier.name,
        agent_server_port=agent_server_port,
        _container=container,
        agent_server_host=agent_server_host,
    )


def _discover_published_port(container: Any, name: str) -> int:
    """Read back the Docker-assigned host port for the agent server.

    Docker needs a moment after `run()` to populate NetworkSettings.Ports for
    a `detach=True` container; reload() forces a fresh inspect.
    """
    container.reload()
    port_bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {})
    bindings = port_bindings.get(_AGENT_SERVER_CONTAINER_PORT)
    if not bindings:
        raise SandboxError(
            f"Sandbox {name} started but agent-server port "
            f"{_AGENT_SERVER_CONTAINER_PORT} was not published."
        )
    try:
        host_port = bindings[0].get("HostPort")
        if host_port is None:
            raise KeyError("HostPort key is missing from bindings")
        return int(host_port)
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise SandboxError(
            f"Sandbox {name} port binding configuration is invalid or missing 'HostPort': {exc}"
        ) from exc


def exec_in_sandbox(
    handle: SandboxHandle,
    cmd: list[str],
    workdir: str | None = None,
) -> tuple[int, str]:
    """Run a command inside the sandbox; return (exit_code, combined_output).

    Used by validation (Step 9) and git operations (Step 3) that run in the
    sandbox's filesystem context.
    """
    try:
        result = handle._container.exec_run(
            cmd=cmd,
            workdir=workdir or handle.repo_mount,
            demux=False,
        )
    except (APIError, DockerException) as exc:
        raise SandboxError(f"exec failed in sandbox {handle.name}: {exc}") from exc

    output = result.output.decode("utf-8", errors="replace") if result.output else ""
    return result.exit_code, output


def teardown_sandbox(handle: SandboxHandle) -> None:
    """Stop + remove the sandbox container. Best-effort; never raises."""
    try:
        handle._container.remove(force=True)
        logger.info("Tore down sandbox %s", handle.name)
    except NotFound:
        pass
    except (APIError, DockerException) as exc:  # pragma: no cover
        logger.warning("Failed to tear down sandbox %s: %s", handle.name, exc)