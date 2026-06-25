"""Composable stimulus primitives and their type registry."""

from .bar import MovingBar
from .base import Stimulus
from .checkerboard import Checkerboard
from .conspecific import Conspecific
from .dark_flash import DarkFlash
from .gradient import LuminanceGradient
from .grating import Grating
from .looming import LoomingDisc
from .okr import RotatingGrating
from .prey import PreyDot
from .rdk import RandomDotKinematogram

STIMULUS_REGISTRY = {
    cls.type: cls
    for cls in (
        Grating,
        LoomingDisc,
        RandomDotKinematogram,
        DarkFlash,
        MovingBar,
        RotatingGrating,
        Checkerboard,
        PreyDot,
        LuminanceGradient,
        Conspecific,
    )
}

__all__ = [
    "Checkerboard",
    "Conspecific",
    "DarkFlash",
    "Grating",
    "LoomingDisc",
    "LuminanceGradient",
    "MovingBar",
    "PreyDot",
    "RandomDotKinematogram",
    "RotatingGrating",
    "STIMULUS_REGISTRY",
    "Stimulus",
]
