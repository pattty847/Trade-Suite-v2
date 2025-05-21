#!/usr/bin/env python3
import logging
from typing import List
from datetime import datetime

from .base import BaseNotifier

logger = logging.getLogger(__name__)

class ConsoleNotifier(BaseNotifier):
    """
    Simple notifier that outputs alerts to the console
    Useful for testing and development
    """
    
    def __init__(self, log_level: int = logging.INFO):
        """
        Initialize console notifier
        
        Args:
            log_level: Logging level to use for notifications
        """
        self.log_level = log_level
    
    def send_notification(self, messages: List[str]) -> bool:
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
    
    def send_test_notification(self) -> bool:
        """Send a test notification"""
        test_message = "This is a test alert notification."
        return self.send_notification([test_message]) 