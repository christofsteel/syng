from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


class Option(Generic[T]):
    pass


@dataclass
class ConfigOption(Generic[T]):
    type: Option[T]
    description: str
    default: T


class BoolOption(Option[bool]):
    pass


class IntOption(Option[int]):
    pass


class StrOption(Option[str]):
    pass


class PasswordOption(Option[str]):
    pass


class FolderOption(Option[str]):
    pass


class FileOption(Option[str]):
    pass


class ListStrOption(Option[list[str]]):
    pass


@dataclass
class ChoiceOption(Option[str]):
    choices: list[str]
