import asyncio
import inspect
import logging
from typing import Callable, Dict, Set, Any, Optional

logger = logging.getLogger("ATTENDANCE_EVENTS")


class AttendanceEventBus:
    """
    Lightweight, thread-safe and asyncio-friendly real-time event bus
    for propagating attendance scan events across active NiceGUI client sessions.
    Allows attendee screens (students, faculty, co-librarians, admins)
    to reflect scan events immediately when a librarian or admin scans their QR code.
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[Callable[[Dict[str, Any]], Any]]] = {}

    def _normalize_key(self, key: Optional[str]) -> str:
        if not key:
            return ""
        k = str(key).strip().upper()
        if k.startswith("LIBRE-ID:"):
            k = k[9:].strip()
        return k

    def subscribe(self, key: str, callback: Callable[[Dict[str, Any]], Any]) -> Callable[[], None]:
        """
        Subscribes a callback to receive scan events for an identifier (institutional_id or user_id)
        or wildcard '*' for all events.
        Returns an unsubscribe callable.
        """
        norm_key = self._normalize_key(key)
        if not norm_key:
            return lambda: None

        if norm_key not in self._subscribers:
            self._subscribers[norm_key] = set()
        self._subscribers[norm_key].add(callback)

        def unsubscribe():
            try:
                if norm_key in self._subscribers:
                    self._subscribers[norm_key].discard(callback)
                    if not self._subscribers[norm_key]:
                        del self._subscribers[norm_key]
            except Exception as e:
                logger.debug(f"Unsubscribe notice: {e}")

        return unsubscribe

    def publish_scan(
        self,
        identifier: str,
        user_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Publishes a scan event to all subscribers matching identifier, user_id, or wildcard '*'.
        Returns the number of subscribers notified.
        """
        payload = dict(event_data or {})
        keys_to_match = {"*"}

        norm_id = self._normalize_key(identifier)
        if norm_id:
            keys_to_match.add(norm_id)

        if user_id:
            norm_uid = self._normalize_key(user_id)
            if norm_uid:
                keys_to_match.add(norm_uid)

        target_callbacks: Set[Callable[[Dict[str, Any]], Any]] = set()
        for k in keys_to_match:
            if k in self._subscribers:
                target_callbacks.update(self._subscribers[k])

        count = len(target_callbacks)
        for cb in target_callbacks:
            try:
                if inspect.iscoroutinefunction(cb):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._safe_async_call(cb, payload))
                    except RuntimeError:
                        asyncio.run(self._safe_async_call(cb, payload))
                else:
                    cb(payload)
            except Exception as err:
                logger.warning(f"Error notifying attendance subscriber: {err}")

        return count

    async def _safe_async_call(self, coro_fn: Callable[[Dict[str, Any]], Any], payload: Dict[str, Any]):
        try:
            await coro_fn(payload)
        except Exception as e:
            logger.debug(f"Async attendance callback error: {e}")

    def get_subscriber_count(self, key: Optional[str] = None) -> int:
        """Returns total active subscribers or subscribers for a specific key."""
        if key is not None:
            norm_key = self._normalize_key(key)
            return len(self._subscribers.get(norm_key, set()))
        return sum(len(s) for s in self._subscribers.values())

    def clear(self):
        """Clears all registered subscribers."""
        self._subscribers.clear()


# Global Singleton instance
attendance_event_bus = AttendanceEventBus()
