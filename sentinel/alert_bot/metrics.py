#!/usr/bin/env python3
import time
import logging
from typing import Dict, Any, Optional, Callable, List
from functools import wraps

# Try to import Prometheus client, gracefully handle if not installed
try:
    import prometheus_client as prom
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Define metrics
if PROMETHEUS_AVAILABLE:
    # Counter for rule evaluations by symbol and rule type
    RULE_EVALUATIONS = prom.Counter(
        'price_alert_rule_evaluations_total',
        'Number of rule evaluations',
        ['symbol', 'rule_type']
    )
    
    # Counter for triggered alerts by symbol and rule type
    ALERTS_TRIGGERED = prom.Counter(
        'price_alert_alerts_triggered_total',
        'Number of alerts triggered',
        ['symbol', 'rule_type']
    )
    
    # Histogram for rule evaluation duration
    RULE_EVAL_DURATION = prom.Histogram(
        'price_alert_rule_evaluation_seconds',
        'Time spent evaluating rules',
        ['symbol', 'rule_type'],
        buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
    )
    
    # Gauge for current price by symbol
    CURRENT_PRICES = prom.Gauge(
        'price_alert_current_price',
        'Current price of the trading symbol',
        ['symbol']
    )
    
    # Counter for notification deliveries by type
    NOTIFICATIONS_SENT = prom.Counter(
        'price_alert_notifications_sent_total',
        'Number of notifications sent',
        ['notifier_type']
    )
    
    # Summary for notification delivery time
    NOTIFICATION_DURATION = prom.Summary(
        'price_alert_notification_duration_seconds',
        'Time spent sending notifications',
        ['notifier_type']
    )
    
    # Gauge for notification queue size
    NOTIFICATION_QUEUE_SIZE = prom.Gauge(
        'price_alert_notification_queue_size',
        'Current size of notification queues',
        ['notifier_type']
    )
else:
    logger.warning("Prometheus client not installed. Metrics will not be collected.")
    # Create no-op metrics as placeholders
    class NoOpMetric:
        def labels(self, *args, **kwargs):
            return self
            
        def inc(self, amount=1):
            pass
            
        def observe(self, value):
            pass
            
        def set(self, value):
            pass
            
        def time(self):
            class TimerContextManager:
                def __enter__(self):
                    return None
                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass
            return TimerContextManager()
    
    RULE_EVALUATIONS = NoOpMetric()
    ALERTS_TRIGGERED = NoOpMetric()
    RULE_EVAL_DURATION = NoOpMetric()
    CURRENT_PRICES = NoOpMetric()
    NOTIFICATIONS_SENT = NoOpMetric()
    NOTIFICATION_DURATION = NoOpMetric()
    NOTIFICATION_QUEUE_SIZE = NoOpMetric()

def track_rule_evaluation(func):
    """
    Decorator to track rule evaluation metrics
    """
    @wraps(func)
    def wrapper(self, current_price, state_manager, extra_data=None):
        # Get symbol and rule type
        symbol = getattr(self, 'symbol', 'unknown')
        rule_type = getattr(self, 'rule_type', 'unknown')
        
        # Track current price
        CURRENT_PRICES.labels(symbol=symbol).set(current_price)
        
        # Increment evaluation counter
        RULE_EVALUATIONS.labels(symbol=symbol, rule_type=rule_type).inc()
        
        # Time the evaluation
        start_time = time.time()
        result = func(self, current_price, state_manager, extra_data)
        duration = time.time() - start_time
        
        # Record duration
        RULE_EVAL_DURATION.labels(symbol=symbol, rule_type=rule_type).observe(duration)
        
        # Track triggered alerts
        if result:
            ALERTS_TRIGGERED.labels(symbol=symbol, rule_type=rule_type).inc()
            
        return result
    return wrapper

def track_notification(notifier_type: str):
    """
    Decorator to track notification metrics
    
    Args:
        notifier_type: Type of notifier (e.g., 'email', 'console')
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, messages, *args, **kwargs):
            # Track queue size
            if hasattr(self, 'queue'):
                NOTIFICATION_QUEUE_SIZE.labels(notifier_type=notifier_type).set(self.queue.qsize())
                
            # Time the notification
            start_time = time.time()
            result = await func(self, messages, *args, **kwargs)
            duration = time.time() - start_time
            
            # Record metrics
            NOTIFICATION_DURATION.labels(notifier_type=notifier_type).observe(duration)
            if result:
                NOTIFICATIONS_SENT.labels(notifier_type=notifier_type).inc()
                
            return result
        return wrapper
    return decorator

async def start_metrics_server(port: int = 9090) -> Optional[Any]:
    """
    Start Prometheus metrics server
    
    Args:
        port: HTTP port to expose metrics on
        
    Returns:
        Server object if Prometheus is available, None otherwise
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning("Prometheus client not installed. Metrics server not started.")
        return None
        
    try:
        logger.info(f"Starting metrics server on port {port}")
        return prom.start_http_server(port)
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        return None 