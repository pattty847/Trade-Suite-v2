#!/usr/bin/env python3
import logging
from typing import List
from datetime import datetime

from .base import AsyncBaseNotifier
from ..metrics import track_notification

logger = logging.getLogger(__name__)

class AsyncConsoleNotifier(AsyncBaseNotifier):
    """
    Asynchronous console notifier for logging alerts to console
    Uses a background worker to decouple logging from rule evaluation
    """
    
    def __init__(self, log_level: int = logging.INFO, max_queue_size: int = 100):
        """
        Initialize async console notifier
        
        Args:
            log_level: Logging level to use for notifications
            max_queue_size: Maximum messages in queue
        """
        super().__init__(max_queue_size=max_queue_size)
        self.log_level = log_level
    
    @track_notification("console")
    async def _send_notification_impl(self, messages: List[str]) -> bool:
        """
        Log alert messages to the console
        
        Args:
            messages: List of alert messages
            
        Returns:
            Always returns True
        """
        if not messages:
            return True  # Nothing to send
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        logger.log(self.log_level, f"=== PRICE ALERTS [{timestamp}] ===")
        for message in messages:
            logger.log(self.log_level, message)
        logger.log(self.log_level, "=" * 30)
        
        return True 