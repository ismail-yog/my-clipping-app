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
    global _db
    if _db is None:
        _db = Database()
    return _db


def get_task_queue() -> TaskQueue:
    global _task_queue
    if _task_queue is None:
        db = get_db()
        _task_queue = TaskQueue(db)
        _task_queue.start()
        # Ensure handlers for vod_process and upload are registered
        get_pipeline_manager()
    return _task_queue


def get_pipeline_manager():
    global _pipeline_manager
    if _pipeline_manager is None:
        from pipeline import PipelineManager
        db = get_db()
        tq = get_task_queue()
        _pipeline_manager = PipelineManager(db, tq)
    return _pipeline_manager
