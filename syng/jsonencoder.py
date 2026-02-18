"""Wraps the ``json`` module, so that own classes get encoded."""

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

from syng.config import Config, serialize_config
from syng.entry import Entry
from syng.result import Result
from syng.song_queue import Queue


class SyngEncoder(json.JSONEncoder):
    """Encoder of :py:class:`Entry`, :py:class`Queue`, :py:class`Result` and UUID.

    Entry and Result are ``dataclasses``, so they are mapped to their
    dictionary representation.

    UUID is represented by its string, and Queue will be represented by a list.
    """

    def default(self, o: Any) -> Any:
        """Implement the encoding.

        Args:
            o: Object to encode

        Returns:
            Encoded version of the object.
        """
        if isinstance(o, Config):
            return serialize_config(o)
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
    """Wrap around ``json.dumps`` with the :py:class:`SyngEncoder`.

    Args:
        obj: Object to dump
        kw: keyword arguments, that are passed to json.dumps

    Returns:
        String representation of the object

    """
    return json.dumps(obj, cls=SyngEncoder, **kw)


def dump(obj: Any, fp: Any, **kw: Any) -> None:
    """Forward everything to ``json.dump``.

    Args:
        obj: Object to dump
        fp: File object to dump into
        kw: keyword arguments, that are passed to json.dump

    """
    json.dump(obj, fp, cls=SyngEncoder, **kw)


def loads(string: str, **kw: Any) -> Any:
    """Forward everything to ``json.loads``.

    Args:
        string: String to load json from
        kw: keyword arguments, that are passed to json.loads

    Returns:
        deserialized object
    """
    return json.loads(string, **kw)


def load(fp: Any, **kw: Any) -> Any:
    """Forward everything to ``json.load``.

    Args:
        fp: File object to read from
        kw: keyword arguments, that are passed to json.load

    Returns:
        deserialized object

    """
    return json.load(fp, **kw)
