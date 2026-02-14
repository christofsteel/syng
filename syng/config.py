from dataclasses import dataclass, is_dataclass
from enum import Enum
from typing import (
    get_args,
    get_origin,
    get_type_hints,
    overload,
)


@dataclass
class Config:
    pass


type _Parsable = dict[str, "_Parsable"] | list["_Parsable"] | str | int | None


def generate_dataclass_from_dict[T](clas: type[T], data: dict[str, _Parsable]) -> T:
    field_types = get_type_hints(clas)
    dataclass_arguments = {
        attribute: generate_class_from_dict(field_types[attribute], value)
        for attribute, value in data.items()
        if attribute in field_types
    }
    return clas(**dataclass_arguments)


def generate_list_from_list[T](clas: type[T], data: list[_Parsable]) -> list[T]:
    return [generate_class_from_dict(clas, item) for item in data]


def generate_enum_from_data[T: Enum](clas: type[T], data: str | int) -> T:
    try:
        enum_value = clas(data)
    except ValueError:
        try:
            enum_value = clas(int(data))
        except ValueError:
            try:
                enum_value = clas(str(data))
            except ValueError as e:
                raise TypeError(
                    f"could not match '{data}' for enum '{clas}'. "
                    f"Possible values are '{list(clas.__members__.values())}'"
                ) from e
    return enum_value


@overload
def generate_class_from_dict[T](clas: type[list[T]], data: _Parsable) -> list[T]: ...
@overload
def generate_class_from_dict[T](clas: type[T], data: _Parsable) -> T: ...


def generate_class_from_dict[T](clas: type[T], data: _Parsable) -> T | list[T]:
    if is_dataclass(clas):
        if not isinstance(data, dict):
            raise TypeError(
                f"got '{data}' of type '{type(data)}, expected 'dict' to create '{clas}'"
            )
        return generate_dataclass_from_dict(clas, data)
    if get_origin(clas) is list:
        if not isinstance(data, list):
            raise TypeError(
                f"got '{data}' of type '{type(data)}, expected 'list' to create '{clas}'"
            )
        inner_class = get_args(clas)[0]
        return generate_list_from_list(inner_class, data)
    if any([clas is t for t in [str, int, bool]]):
        if not isinstance(data, clas):
            raise TypeError(f"got '{data} of type '{type(data)}', expected '{clas}'")
        return data
    if issubclass(clas, Enum):
        if not isinstance(data, str) or isinstance(data, int):
            raise TypeError(
                f"got '{data} of type '{type(data)}, expected 'str' or 'int' to create {clas}"
            )
        return generate_enum_from_data(clas, data)

    raise TypeError(f"unsupported field type '{clas}'")
