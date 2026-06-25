"""Composable stimulus primitives and their type registry."""

from .bar import MovingBar
from .base import Stimulus
from .dark_flash import DarkFlash
from .grating import Grating
from .looming import LoomingDisc
from .rdk import RandomDotKinematogram

STIMULUS_REGISTRY = {
    cls.type: cls
    for cls in (Grating, LoomingDisc, RandomDotKinematogram, DarkFlash, MovingBar)
}

__all__ = [
    "DarkFlash",
    "Grating",
    "LoomingDisc",
    "MovingBar",
    "RandomDotKinematogram",
    "STIMULUS_REGISTRY",
    "Stimulus",
]
