"""Platform detection for shadow environments.

Detects the current platform and provides appropriate warnings or configurations.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Platform(Enum):
    """Supported platforms for shadow environments."""

    WSL2 = "wsl2"
    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"
    CODESPACES = "codespaces"
    UNKNOWN = "unknown"


@dataclass
class PlatformInfo:
    """Information about the current platform."""

    platform: Platform
    docker_available: bool
    compose_available: bool
    warnings: list[str]
    recommendations: list[str]

    @property
    def ready(self) -> bool:
        """Check if platform is ready for shadow environments."""
        return self.docker_available and self.compose_available


def _is_wsl() -> bool:
    """Check if running in WSL."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


def _is_codespaces() -> bool:
    """Check if running in GitHub Codespaces."""
    return os.environ.get("CODESPACES") == "true"


def _is_macos() -> bool:
    """Check if running on macOS."""
    import platform

    return platform.system() == "Darwin"


def _is_windows() -> bool:
    """Check if running on Windows (native, not WSL)."""
    import platform

    return platform.system() == "Windows" and not _is_wsl()


def _check_docker() -> bool:
    """Check if Docker is available."""
    return shutil.which("docker") is not None


def _check_compose() -> bool:
    """Check if Docker Compose is available."""
    # Try docker compose (v2)
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, PermissionError):
        pass

    # Try docker-compose (v1)
    return shutil.which("docker-compose") is not None


def _is_windows_mount(path: Path) -> bool:
    """Check if path is a Windows mount in WSL (slower performance)."""
    try:
        return str(path.resolve()).startswith("/mnt/")
    except (OSError, PermissionError):
        return False


def detect_platform() -> PlatformInfo:
    """Detect current platform and check readiness for shadow environments.

    Returns:
        PlatformInfo with platform details, availability, and recommendations
    """
    warnings: list[str] = []
    recommendations: list[str] = []

    # Detect platform
    if _is_codespaces():
        platform = Platform.CODESPACES
        recommendations.append("Codespaces detected. Docker-in-Docker should be available via features.")
    elif _is_wsl():
        platform = Platform.WSL2
        # Check for Windows mount paths
        if _is_windows_mount(Path.cwd()):
            warnings.append(
                "Working directory is on Windows filesystem (/mnt/c/...).\n"
                "Performance will be significantly slower.\n"
                "Consider working from ~/... instead."
            )
    elif _is_macos():
        platform = Platform.MACOS
        recommendations.append("macOS detected. Docker Desktop or OrbStack recommended for best performance.")
    elif _is_windows():
        platform = Platform.WINDOWS
        warnings.append(
            "Native Windows detected. WSL2 is strongly recommended for better performance.\n"
            "Consider running from within WSL2 instead."
        )
    else:
        platform = Platform.LINUX

    # Check Docker availability
    docker_available = _check_docker()
    compose_available = _check_compose()

    if not docker_available:
        warnings.append(
            "Docker not found. Install Docker to use shadow environments:\n  https://docs.docker.com/get-docker/"
        )
    elif not compose_available:
        warnings.append("Docker Compose not found. Install Docker Compose:\n  https://docs.docker.com/compose/install/")

    return PlatformInfo(
        platform=platform,
        docker_available=docker_available,
        compose_available=compose_available,
        warnings=warnings,
        recommendations=recommendations,
    )


def print_platform_status() -> PlatformInfo:
    """Print platform status and return info."""
    info = detect_platform()

    print(f"Platform: {info.platform.value}")
    print(f"Docker: {'✓' if info.docker_available else '✗'}")
    print(f"Compose: {'✓' if info.compose_available else '✗'}")

    if info.warnings:
        print("\nWarnings:")
        for warning in info.warnings:
            for line in warning.split("\n"):
                print(f"  ⚠️  {line}")

    if info.recommendations:
        print("\nRecommendations:")
        for rec in info.recommendations:
            for line in rec.split("\n"):
                print(f"  💡 {line}")

    if info.ready:
        print("\n✓ Ready for shadow environments")
    else:
        print("\n✗ Not ready for shadow environments")

    return info
