"""Model registry for the research-grade stimulus generator."""

from models.base import BaseModel
from models.boids import ResearchBoidsModel
from models.hybrid import HybridConsensusModel
from models.potential_field import PotentialFieldModel
from models.vicsek import VicsekConsensusModel

MODEL_REGISTRY = {
    ResearchBoidsModel.name: ResearchBoidsModel,
    VicsekConsensusModel.name: VicsekConsensusModel,
    PotentialFieldModel.name: PotentialFieldModel,
    HybridConsensusModel.name: HybridConsensusModel,
}


def build_model(model_name: str) -> BaseModel:
    """Instantiate the requested model or fall back to the default."""
    model_class = MODEL_REGISTRY.get(model_name, HybridConsensusModel)
    return model_class()


__all__ = [
    "BaseModel",
    "HybridConsensusModel",
    "MODEL_REGISTRY",
    "PotentialFieldModel",
    "ResearchBoidsModel",
    "VicsekConsensusModel",
    "build_model",
]
