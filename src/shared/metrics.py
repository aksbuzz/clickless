"""
Prometheus metrics for workflow automation system.
"""
from prometheus_client import Counter, Histogram, Gauge, Info

# Workflow Instance Metrics
workflow_started_total = Counter(
    'workflow_started_total',
    'Total number of workflow instances started',
    ['workflow_name']
)

workflow_completed_total = Counter(
    'workflow_completed_total',
    'Total number of workflow instances completed',
    ['workflow_name', 'status']  # status: completed, failed, cancelled
)

workflow_duration_seconds = Histogram(
    'workflow_duration_seconds',
    'Duration of workflow executions in seconds',
    ['workflow_name', 'status'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]  # 1s to 1h
)

# Step Execution Metrics
step_execution_total = Counter(
    'step_execution_total',
    'Total number of step executions',
    ['workflow_name', 'step_name', 'status']
)

step_duration_seconds = Histogram(
    'step_duration_seconds',
    'Duration of step executions in seconds',
    ['workflow_name', 'step_name', 'action_type'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300]  # 100ms to 5min
)

step_retry_total = Counter(
    'step_retry_total',
    'Total number of step retries',
    ['workflow_name', 'step_name']
)

# System Metrics
active_workflows = Gauge(
    'active_workflows',
    'Number of currently active (running) workflows'
)

celery_queue_depth = Gauge(
    'celery_queue_depth',
    'Number of tasks in Celery queues',
    ['queue_name']
)

# Error Metrics
workflow_errors_total = Counter(
    'workflow_errors_total',
    'Total number of workflow errors',
    ['workflow_name', 'error_type']
)

# API Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)

# System Info
app_info = Info('app', 'Application information')
app_info.info({
    'version': '0.1.0',
    'name': 'workflow_automate'
})
