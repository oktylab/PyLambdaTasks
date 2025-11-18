import json, uuid, datetime, dataclasses
from decimal import Decimal
from typing import Dict, Callable, Any, Type

# ==============================================================================
# Default Type Handlers Registry
# ==============================================================================

_DEFAULT_TYPE_HANDLERS: Dict[Type, Callable[[Any], Any]] = {
    datetime.datetime: lambda dt: dt.isoformat(),
    datetime.date: lambda d: d.isoformat(),
    datetime.time: lambda t: t.isoformat(),
    uuid.UUID: lambda u: str(u),
    Decimal: lambda d: float(d),
}

# ==============================================================================
# Core Encoder Class
# ==============================================================================

class CustomJsonEncoder(json.JSONEncoder):
    """
    A custom JSON encoder that can handle additional types and be extended.
    """
    # The registry is a class variable, so it can be modified by the public
    # `add_serializer` function and affect all subsequent serializations.
    _TYPE_HANDLERS: Dict[Type, Callable[[Any], Any]] = _DEFAULT_TYPE_HANDLERS.copy()

    def default(self, o: Any) -> Any:
        """
        The core method called by `json.dumps` for non-standard objects.
        """
        # First, handle dataclasses specifically, as they are a common case.
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)

        # Iterate through our registered handlers to find one that matches.
        for type_class, handler in self._TYPE_HANDLERS.items():
            if isinstance(o, type_class):
                return handler(o)
        
        # If no handler is found, fall back to the default JSONEncoder behavior,
        # which will raise a TypeError for unserializable types.
        return super().default(o)

# ==============================================================================
# Public API
# ==============================================================================

def add_serializer(type_to_encode: Type, handler: Callable[[Any], Any]) -> None:
    """
    Registers a new custom serializer for a given type.

    This allows end-users to extend the JSON serialization capabilities for
    their own custom classes.

    Example:
        class MyObject:
            def __init__(self, value):
                self.value = value

        def my_object_serializer(obj: MyObject) -> dict:
            return {"my_value": obj.value}

        add_serializer(MyObject, my_object_serializer)
    
    Args:
        type_to_encode: The class/type to be serialized (e.g., `MyObject`).
        handler: A function that takes an instance of the type and returns a
                 JSON-serializable representation.
    """
    CustomJsonEncoder._TYPE_HANDLERS[type_to_encode] = handler


def serialize_to_json_str(data: Any, **kwargs: Any) -> str:
    """
    Serializes a Python object to a JSON formatted string using the custom encoder.

    This function acts as a drop-in replacement for `json.dumps`, providing
    out-of-the-box support for many common types.

    Args:
        data: The Python object to serialize.
        **kwargs: Any standard keyword arguments for `json.dumps` (e.g., `indent`).

    Returns:
        A JSON formatted string.
    """
    return json.dumps(data, cls=CustomJsonEncoder, **kwargs)