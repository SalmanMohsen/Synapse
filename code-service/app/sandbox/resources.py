"""Resource tiering for sandbox containers (build plan Step 2 / Resources).

Combined request/ceiling model, mirroring how Kubernetes separates resource
*requests* from *limits*:

  1. Inspect the cloned repo (size, presence of package.json / build tooling)
     and pick a tier request.
  2. Cap the actual allocation at a safety margin of currently-free host
     resources (never request more than ~75% of what's free).
  3. If even the reduced allocation can't be satisfied, the caller treats it as
     a Hard Technical failure — same shape as any other "couldn't start" case.

The tier table is intentionally minimal (static, node_project); add tiers as
real repos beyond HTML/CSS are actually tested.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Fraction of currently-free host resources we are willing to hand to a single
# sandbox. Keeps headroom for the host + other concurrent runs.
HOST_SAFETY_MARGIN = 0.75


@dataclass(frozen=True)
class ResourceTier:
    name: str
    # nano_cpus: Docker's CPU quota unit (1 CPU == 1_000_000_000).
    cpus: float
    # memory in bytes.
    mem_bytes: int


TIER_STATIC = ResourceTier(name="static", cpus=1.0, mem_bytes=1 * 1024**3)
TIER_NODE_PROJECT = ResourceTier(name="node_project", cpus=2.0, mem_bytes=2 * 1024**3)


class InsufficientResourcesError(RuntimeError):
    """Raised when even the host-capped allocation can't be satisfied."""


def select_tier(repo_path: str) -> ResourceTier:
    """Pick a request tier from cheap, deterministic repo inspection."""
    has_package_json = os.path.isfile(os.path.join(repo_path, "package.json"))
    if has_package_json:
        return TIER_NODE_PROJECT
    return TIER_STATIC


def _free_host_resources() -> tuple[float, int]:
    """Return (free_cpus, free_mem_bytes) as best the host exposes.

    Uses os.sched_getaffinity for CPU count and /proc/meminfo MemAvailable for
    memory on Linux (the deployment target). Falls back conservatively.
    """
    try:
        cpu_count = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        cpu_count = os.cpu_count() or 1

    free_mem = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    # value is in kB
                    free_mem = int(line.split()[1]) * 1024
                    break
    except (OSError, ValueError):
        free_mem = 0

    return float(cpu_count), free_mem


def resolve_allocation(repo_path: str) -> ResourceTier:
    """Return the effective allocation: the requested tier capped by host margin.

    Raises InsufficientResourcesError if the capped allocation would fall below
    a floor that makes the sandbox non-viable.
    """
    requested = select_tier(repo_path)
    free_cpus, free_mem = _free_host_resources()

    if free_cpus <= 0 or free_mem <= 0:
        # Can't reason about capacity; hand back the request and let container
        # creation fail loudly (treated as Hard Technical upstream).
        logger.warning("Could not read host capacity; using uncapped tier %s", requested.name)
        return requested

    cpu_ceiling = free_cpus * HOST_SAFETY_MARGIN
    mem_ceiling = int(free_mem * HOST_SAFETY_MARGIN)

    effective_cpus = min(requested.cpus, cpu_ceiling)
    effective_mem = min(requested.mem_bytes, mem_ceiling)

    # Viability floor: below this the sandbox can't realistically run tooling.
    MIN_CPUS = 0.5
    MIN_MEM = 512 * 1024**2
    if effective_cpus < MIN_CPUS or effective_mem < MIN_MEM:
        raise InsufficientResourcesError(
            f"Host cannot satisfy minimum sandbox allocation: "
            f"capped to {effective_cpus:.2f} CPU / {effective_mem // 1024**2} MB "
            f"(free: {free_cpus:.2f} CPU / {free_mem // 1024**2} MB)"
        )

    if effective_cpus < requested.cpus or effective_mem < requested.mem_bytes:
        logger.info(
            "Tier %s capped by host margin: %.2f CPU / %d MB (requested %.2f / %d)",
            requested.name,
            effective_cpus,
            effective_mem // 1024**2,
            requested.cpus,
            requested.mem_bytes // 1024**2,
        )

    return ResourceTier(name=requested.name, cpus=effective_cpus, mem_bytes=effective_mem)
