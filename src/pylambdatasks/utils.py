import json, uuid, datetime, dataclasses
from decimal import Decimal
from typing import Dict, Callable, Any, Type

# ==============================================================================
# ==============================================================================

_DEFAULT_TYPE_HANDLERS: Dict[Type, Callable[[Any], Any]] = {
    datetime.datetime: lambda dt: dt.isoformat(),
    datetime.date: lambda d: d.isoformat(),
    datetime.time: lambda t: t.isoformat(),
    uuid.UUID: lambda u: str(u),
    Decimal: lambda d: float(d),
}

# ==============================================================================
# ==============================================================================
class CustomJsonEncoder(json.JSONEncoder):
    _TYPE_HANDLERS: Dict[Type, Callable[[Any], Any]] = _DEFAULT_TYPE_HANDLERS.copy()

    def default(self, o: Any) -> Any:
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)

        for type_class, handler in self._TYPE_HANDLERS.items():
            if isinstance(o, type_class):
                return handler(o)
        return super().default(o)

# ==============================================================================
# ==============================================================================
def add_serializer(type_to_encode: Type, handler: Callable[[Any], Any]) -> None:
    CustomJsonEncoder._TYPE_HANDLERS[type_to_encode] = handler


def serialize_to_json_str(data: Any, **kwargs: Any) -> str:
    return json.dumps(data, cls=CustomJsonEncoder, **kwargs)