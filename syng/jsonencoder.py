"""Wraps the ``json`` module, so that own classes get encoded."""

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

from .entry import Entry
from .queue import Queue
from .result import Result


class SyngEncoder(json.JSONEncoder):
    """
    Encoder of :py:class:`Entry`, :py:class`Queue`, :py:class`Result` and UUID.

    Entry and Result are ``dataclasses``, so they are mapped to their
    dictionary representation.

    UUID is repersented by its string, and Queue will be represented by a list.
    """

    def default(self, o: Any) -> Any:
        """Implement the encoding."""
        if isinstance(o, Entry):
            return asdict(o)
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, Result):
            return asdict(o)
        if isinstance(o, Queue):
            return o.to_list()
        return json.JSONEncoder.default(self, o)


def dumps(obj: Any, **kw: Any) -> str:
    """Wrap around ``json.dump`` with the :py:class:`SyngEncoder`."""
    return json.dumps(obj, cls=SyngEncoder, **kw)


def loads(string: str, **kw: Any) -> Any:
    """Forward everything to ``json.loads``."""
    return json.loads(string, **kw)
