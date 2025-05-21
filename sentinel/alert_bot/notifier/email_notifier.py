#!/usr/bin/env python3
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from datetime import datetime

from .base import BaseNotifier

logger = logging.getLogger(__name__)

class EmailNotifier(BaseNotifier):
    """
    Notifier that sends alerts via email
    """
    
    def __init__(self, 
                 smtp_server: Optional[str] = None,
                 smtp_port: Optional[int] = None,
                 smtp_username: Optional[str] = None,
                 smtp_password: Optional[str] = None,
                 recipient_email: Optional[str] = None,
                 use_env_vars: bool = True):
        """
        Initialize the email notifier
        
        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            smtp_username: SMTP username/email
            smtp_password: SMTP password
            recipient_email: Email to send alerts to
            use_env_vars: Whether to load config from environment variables
        """
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
    
    def send_notification(self, messages: List[str]) -> bool:
        """
        Send email notification with the given alert messages
        
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
    
    def send_test_notification(self) -> bool:
        """
        Send a test email to verify configuration
        
        Returns:
            True if sent successfully, False otherwise
        """
        test_message = (
            f"Test Alert\n\n"
            f"This is a test message to verify your email configuration is working correctly.\n\n"
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.info("Sending test email...")
        return self.send_notification([test_message]) 