"""Actor context for Hippo SDK — Decision 9.6.G.

Provides a ContextVar that carries the current actor UUID across a call
stack without threading it explicitly through every write method.

Usage patterns:
- FastAPI / HTTP: middleware calls ``set_actor(actor_id)`` at request entry.
- Direct SDK: wrap calls with ``with_actor(actor_id):``.
- Explicit override: pass ``actor_id=`` directly to ``ProvenanceStore.record()``.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator, Optional

# Module-level ContextVar; default is None (unset / anonymous).
current_actor: ContextVar[Optional[str]] = ContextVar("current_actor", default=None)


def get_current_actor() -> Optional[str]:
    """Return the actor UUID set in the current context, or None."""
    return current_actor.get()


def set_actor(actor_id: Optional[str]) -> object:
    """Set the actor for the current context. Returns a reset token.

    Callers that want to restore the previous value should call
    ``current_actor.reset(token)`` when done.  The ``with_actor``
    context manager does this automatically.
    """
    return current_actor.set(actor_id)


@contextmanager
def with_actor(actor_id: str) -> Generator[None, None, None]:
    """Context manager that sets the current actor for a block of code.

    Example::

        with with_actor("agent-uuid-here"):
            client.create("Sample", {...})
    """
    token = current_actor.set(actor_id)
    try:
        yield
    finally:
        current_actor.reset(token)
