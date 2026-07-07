"""Email collector helpers."""

from .events import email_to_event, emails_to_events, write_events_jsonl

__all__ = ["email_to_event", "emails_to_events", "write_events_jsonl"]
