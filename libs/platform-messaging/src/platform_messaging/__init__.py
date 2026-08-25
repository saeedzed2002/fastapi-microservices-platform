"""Technical messaging primitives shared across bounded contexts."""

from platform_messaging.kafka_dlq import KafkaDlqPolicy, process_record_with_dead_letter

__all__ = ["KafkaDlqPolicy", "process_record_with_dead_letter"]
