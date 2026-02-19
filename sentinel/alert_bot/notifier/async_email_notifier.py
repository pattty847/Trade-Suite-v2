#!/usr/bin/env python3
import os
import smtplib
import logging
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import AsyncBaseNotifier
from ..metrics import track_notification

logger = logging.getLogger(__name__)

class AsyncEmailNotifier(AsyncBaseNotifier):
    """
    Asynchronous email notifier for sending alert emails
    Uses a background worker to decouple sending from rule evaluation
    """
    
    def __init__(self, 
                 smtp_server: Optional[str] = None,
                 smtp_port: Optional[int] = None,
                 smtp_username: Optional[str] = None,
                 smtp_password: Optional[str] = None,
                 recipient_email: Optional[str] = None,
                 use_env_vars: bool = True,
                 max_queue_size: int = 100):
        """
        Initialize the async email notifier
        
        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            smtp_username: SMTP username/email
            smtp_password: SMTP password
            recipient_email: Email to send alerts to
            use_env_vars: Whether to load config from environment variables
            max_queue_size: Maximum messages in queue
        """
        super().__init__(max_queue_size=max_queue_size)
        
        # Set up from parameters
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.recipient_email = recipient_email
        
        # Override with environment variables if requested
        if use_env_vars:
            self.smtp_server = os.getenv('SMTP_SERVER', self.smtp_server or 'smtp.gmail.com')
            self.smtp_port = int(os.getenv('SMTP_PORT', self.smtp_port or 587))
            self.smtp_username = os.getenv('SMTP_USERNAME', self.smtp_username)
            self.smtp_password = os.getenv('SMTP_PASSWORD', self.smtp_password)
            self.recipient_email = os.getenv('ALERT_EMAIL', self.recipient_email)
        
        self._check_config()
    
    def _check_config(self) -> None:
        """Check if the email configuration is complete"""
        missing = []
        if not self.smtp_server:
            missing.append("SMTP server")
        if not self.smtp_port:
            missing.append("SMTP port")
        if not self.smtp_username:
            missing.append("SMTP username/email")
        if not self.smtp_password:
            missing.append("SMTP password")
        if not self.recipient_email:
            missing.append("recipient email")
            
        if missing:
            logger.warning(f"Email notifier is missing configuration: {', '.join(missing)}")
            logger.warning("Email alerts will not be sent until configuration is complete")
    
    @track_notification("email")
    async def _send_notification_impl(self, messages: List[str]) -> bool:
        """
        Asynchronously send email notification with the given alert messages
        
        Args:
            messages: List of alert messages to include
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not messages:
            return True  # Nothing to send
            
        if not all([self.smtp_server, self.smtp_port, self.smtp_username, 
                   self.smtp_password, self.recipient_email]):
            logger.warning("Email configuration incomplete. Skipping notification.")
            return False
        
        # Run the email sending in a separate thread using loop.run_in_executor
        # This is because smtplib is not async-compatible
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._send_email_sync, messages)
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False
    
    def _send_email_sync(self, messages: List[str]) -> bool:
        """
        Synchronous implementation of email sending
        
        Args:
            messages: List of alert messages
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.recipient_email
            msg['Subject'] = f"Crypto Price Alert - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            body = "\n\n".join(messages)
            msg.attach(MIMEText(body, 'plain'))
            
            # Connect to SMTP server
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            
            # Send email
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Sent {len(messages)} alert(s) to {self.recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False 