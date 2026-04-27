"""Pluggable notification channel protocol.

v1 ships only the SMTP implementation; webhook/Slack come later.
"""
from __future__ import annotations

from typing import Protocol


class NotificationChannel(Protocol):
    type: str  # email | webhook | slack

    async def deliver(self, *, subject: str, body: str, config: dict) -> None: ...


_REGISTRY: dict[str, NotificationChannel] = {}


def register(channel: NotificationChannel) -> None:
    _REGISTRY[channel.type] = channel


def get(channel_type: str) -> NotificationChannel:
    if channel_type not in _REGISTRY:
        raise KeyError(f"unknown channel type: {channel_type}")
    return _REGISTRY[channel_type]


def types() -> list[str]:
    return list(_REGISTRY.keys())
