from typing import Dict, Optional, List

import asyncio

import ray
from ray.util.queue import Queue as RayQueue, _QueueActor


class Unavailable:
    """No object should be instance of this class"""

    def __init__(self):
        raise RuntimeError("This class should never be instantiated.")


class _EventActor:
    def __init__(self):
        self._event = asyncio.Event()

    def set(self):
        self._event.set()

    def clear(self):
        self._event.clear()

    def is_set(self):
        return self._event.is_set()


_RemoteEventActor = ray.remote(_EventActor)


class Event:
    def __init__(self,
                 actor_options: Optional[Dict] = None,
                 actor_cls: Optional[ray.actor.ActorClass] = None) -> None:
        actor_cls = actor_cls or _RemoteEventActor
        actor_options = {} if not actor_options else actor_options
        self.actor = actor_cls.options(**actor_options).remote()

    def set(self):
        self.actor.set.remote()

    def clear(self):
        self.actor.clear.remote()

    def is_set(self):
        return ray.get(self.actor.is_set.remote())

    def shutdown(self):
        if self.actor:
            ray.kill(self.actor)
        self.actor = None


_RemoteQueueActor = ray.remote(_QueueActor)


class Queue(RayQueue):
    def __init__(self,
                 maxsize: int = 0,
                 actor_options: Optional[Dict] = None,
                 actor_cls: Optional[ray.actor.ActorClass] = None) -> None:
        actor_cls = actor_cls or _RemoteEventActor
        actor_options = actor_options or {}
        self.maxsize = maxsize
        self.actor = actor_cls.options(**actor_options).remote(self.maxsize)


class MultiActorTask:
    """Utility class to hold multiple futures.

    The `is_ready()` method will return True once all futures are ready.

    Args:
        pending_futures (list): List of object references (futures)
            that should be tracked.
    """

    def __init__(self, pending_futures: Optional[List[ray.ObjectRef]] = None):
        self._pending_futures = pending_futures or []
        self._ready_futures = []

    def is_ready(self):
        if not self._pending_futures:
            return True

        ready = True
        while ready:
            ready, not_ready = ray.wait(self._pending_futures, timeout=0)
            if ready:
                for obj in ready:
                    self._pending_futures.remove(obj)
                    self._ready_futures.append(obj)

        return not bool(self._pending_futures)


_exported_remote_actors = False


def export_remote_actors():
    """Export remote actors to avoid multi export e.g. in Ray Tune"""
    global _exported_remote_actors

    if not _exported_remote_actors:
        dummy_event = _RemoteEventActor.remote()  # noqa: F841
        dummy_queue = _RemoteQueueActor.remote(maxsize=1)  # noqa: F841
        _exported_remote_actors = True
