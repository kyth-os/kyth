"""Lazy mixin composition for multi-tab Hub pages.

Page modules define a shell class that subclasses ``Page`` only. On first
construction, mixins are imported and a composed subclass is built so the
expensive tab modules are not paid at import time (only when the user opens
that hub).
"""
from __future__ import annotations

from typing import Callable


def compose_on_first_init(load_mixins: Callable[[], tuple[type, ...]]):
    """Decorator: first ``Shell()`` builds ``type(Shell, *mixins)``.

    Usage::

        def _load_mixins():
            from .page_foo import _FooMixin
            return (_FooMixin,)

        @compose_on_first_init(_load_mixins)
        class FooPage(Page):
            ...
    """

    def decorator(shell_cls: type) -> type:
        state: dict[str, type | None] = {"impl": None}

        def __new__(cls, *args, **kwargs):  # noqa: N807
            if cls is shell_cls:
                impl = state["impl"]
                if impl is None:
                    mixins = load_mixins()
                    impl = type(shell_cls.__name__, (shell_cls, *mixins), {})
                    state["impl"] = impl
                return object.__new__(impl)
            return object.__new__(cls)

        shell_cls.__new__ = staticmethod(__new__)  # type: ignore[method-assign, assignment]
        return shell_cls

    return decorator
