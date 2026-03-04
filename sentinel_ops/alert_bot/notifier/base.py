#!/usr/bin/env python3
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Any, Union

logger = logging.getLogger(__name__)

class AsyncBaseNotifier(ABC):
    """
    Abstract base class for all async alert notifiers
    
    Features:
    - Async notification methods
    - Queue-based message processing
    - Background worker for processing notifications
    """
    
    def __init__(self, max_queue_size: int = 100):
        """
        Initialize the async notifier
        
        Args:
            max_queue_size: Maximum number of pending notifications in queue
        """
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.worker_task = None
        self.running = False
        
    async def start(self):
        """Start the notification worker"""
        if self.running:
            return
            
        self.running = True
        self.worker_task = asyncio.create_task(self._notification_worker())
        logger.debug(f"{self.__class__.__name__} worker started")
        
    async def stop(self):
        """Stop the notification worker"""
        if not self.running:
            return
            
        self.running = False
        
        # Wait for the queue to be processed
        if not self.queue.empty():
            logger.info(f"Waiting for {self.queue.qsize()} pending notifications to be processed...")
            await self.queue.join()
            
        # Cancel the worker task
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
                
        logger.debug(f"{self.__class__.__name__} worker stopped")
    
    async def _notification_worker(self):
        """Background worker that processes the notification queue"""
        while self.running:
            try:
                # Get message from queue
                message = await self.queue.get()
                
                try:
                    # Process the message
                    await self._send_notification_impl(message)
                except Exception as e:
                    logger.error(f"Error sending notification: {e}")
                finally:
                    # Mark task as done
                    self.queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in notification worker: {e}")
                await asyncio.sleep(1)  # Avoid tight loop on errors
    
    async def queue_notification(self, message: Union[str, List[str]]) -> bool:
        """
        Queue a notification to be sent asynchronously
        
        Args:
            message: String or list of strings to send
            
        Returns:
            True if queued successfully, False if queue is full
        """
        try:
            # Convert single string to list
            if isinstance(message, str):
                message = [message]
                
            await self.queue.put(message)
            return True
        except asyncio.QueueFull:
            logger.error(f"Notification queue is full, dropping message")
            return False
    
    @abstractmethod
    async def _send_notification_impl(self, messages: List[str]) -> bool:
        """
        Actual implementation of sending a notification
        
        Args:
            messages: List of alert messages to send
            
        Returns:
            True if notification was sent successfully, False otherwise
        """
        pass
    
    async def send_test_notification(self) -> bool:
        """Send a test notification"""
        from datetime import datetime
        test_message = f"This is a test alert notification. Time: {datetime.now().isoformat()}"
        return await self.queue_notification(test_message)


# Keep the original synchronous base class for backward compatibility
class BaseNotifier(ABC):
    """
    Abstract base class for all alert notifiers (synchronous version)
    """
    
    @abstractmethod
    def send_notification(self, messages: List[str]) -> bool:
        """
        Send notifications with the given messages
        
        Args:
            messages: List of alert messages to send
            
        Returns:
            True if notification was sent successfully, False otherwise
        """
        pass 