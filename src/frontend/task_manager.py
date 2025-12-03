"""In-memory task manager for tracking alert analysis jobs.

This module provides a simple in-memory task tracking system
for managing async analysis tasks. Suitable for POC use.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """Represents an analysis task.

    Attributes:
        task_id: Unique identifier for the task
        status: Current status (processing, complete, error)
        alert_id: ID extracted from the alert XML
        alert_type: Type of alert (insider_trading, wash_trade)
        decision: The analysis decision JSON
        error: Error message if status is error
        created_at: Timestamp when task was created
    """

    task_id: str
    status: str = "processing"
    alert_id: Optional[str] = None
    alert_type: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class TaskManager:
    """In-memory task manager for tracking analysis jobs.

    This class provides methods for creating, updating, and
    retrieving analysis tasks. Tasks are stored in memory
    and are lost on server restart.

    Attributes:
        tasks: Dictionary mapping task_id to Task objects
        max_age_hours: Maximum age of tasks before cleanup
    """

    def __init__(self, max_age_hours: int = 1) -> None:
        """Initialize the task manager.

        Args:
            max_age_hours: Hours after which tasks are eligible for cleanup
        """
        self.tasks: Dict[str, Task] = {}
        self.max_age_hours = max_age_hours
        logger.info(f"TaskManager initialized with max_age_hours={max_age_hours}")

    def create_task(self, task_id: str) -> Task:
        """Create a new task with processing status.

        Args:
            task_id: Unique identifier for the task

        Returns:
            The newly created Task object
        """
        task = Task(task_id=task_id)
        self.tasks[task_id] = task
        logger.info(f"Created task: {task_id}")
        return task

    def update_task(
        self,
        task_id: str,
        status: str,
        alert_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        decision: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[Task]:
        """Update an existing task.

        Args:
            task_id: ID of the task to update
            status: New status (processing, complete, error)
            alert_id: Alert ID from the XML
            alert_type: Type of alert
            decision: Analysis decision JSON
            error: Error message if applicable

        Returns:
            Updated Task object or None if not found
        """
        task = self.tasks.get(task_id)
        if task is None:
            logger.warning(f"Task not found for update: {task_id}")
            return None

        task.status = status
        if alert_id is not None:
            task.alert_id = alert_id
        if alert_type is not None:
            task.alert_type = alert_type
        if decision is not None:
            task.decision = decision
        if error is not None:
            task.error = error

        logger.info(f"Updated task {task_id}: status={status}")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID.

        Args:
            task_id: ID of the task to retrieve

        Returns:
            Task object or None if not found
        """
        task = self.tasks.get(task_id)
        if task:
            logger.debug(f"Retrieved task {task_id}: status={task.status}")
        else:
            logger.debug(f"Task not found: {task_id}")
        return task

    def cleanup_old_tasks(self) -> int:
        """Remove tasks older than max_age_hours.

        Returns:
            Number of tasks removed
        """
        cutoff = datetime.utcnow() - timedelta(hours=self.max_age_hours)
        old_task_ids = [
            task_id
            for task_id, task in self.tasks.items()
            if task.created_at < cutoff
        ]

        for task_id in old_task_ids:
            del self.tasks[task_id]

        if old_task_ids:
            logger.info(f"Cleaned up {len(old_task_ids)} old tasks")

        return len(old_task_ids)

    def get_all_tasks(self) -> Dict[str, Task]:
        """Get all tasks.

        Returns:
            Dictionary of all tasks
        """
        return self.tasks.copy()
