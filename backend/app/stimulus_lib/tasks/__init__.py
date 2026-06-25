"""Task catalog: named paradigms users choose from."""

from .catalog import TASK_REGISTRY, build_task, list_tasks

__all__ = ["TASK_REGISTRY", "build_task", "list_tasks"]
