"""Amplifier Shadow Environment Management.

Shadow environments are isolated, ephemeral development environments that enable
safe experimentation and validation of the full Amplifier remote-install experience.
"""

from amplifier_shadow.gateway import ExecResult, ShadowGateway
from amplifier_shadow.platform import Platform, PlatformInfo, detect_platform

__all__ = [
    "ExecResult",
    "Platform",
    "PlatformInfo",
    "ShadowGateway",
    "detect_platform",
]
__version__ = "0.1.0"
