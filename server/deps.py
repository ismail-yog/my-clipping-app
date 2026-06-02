"""
StreamClipper — FastAPI Dependencies
Shared state holders injected into route handlers.
"""

from typing import Optional
from database import Database
from task_queue import TaskQueue

# Singleton references set at app startup
_db: Optional[Database] = None
_pipeline_manager = None  # PipelineManager
_task_queue: Optional[TaskQueue] = None


def set_dependencies(db: Database, pipeline_manager=None, task_queue: TaskQueue = None):
    global _db, _pipeline_manager, _task_queue
    _db = db
    _pipeline_manager = pipeline_manager
    _task_queue = task_queue


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


def get_pipeline_manager():
    return _pipeline_manager


def get_task_queue() -> Optional[TaskQueue]:
    return _task_queue
