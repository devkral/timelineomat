from abc import ABC, abstractmethod
from collections.abc import Callable, MutableMapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime as dt
from functools import wraps
from typing import Any, ClassVar, Self, dataclass_transform


@dataclass
class TMField:
    name: str | None = None
    serializer: Callable[[Any], Any] = field(default=lambda x: x)
    deserializer: Callable[[Any], Any] = field(default=lambda x: x)


@dataclass_transform(field_specifiers=(TMField,))
class BaseTMSnapshot(ABC):
    snapshot_for: dt
    data: MutableMapping[str, Any]
    full: bool
    model_type: str
    _snapshot_accessors_wrapped: ClassVar[bool] = False
    managed: set[str]
    _snapshots: list[Self] | None = None

    @abstractmethod
    def get_snapshot(self, *, after: dt | None = None, before: dt | None = None) -> Self:
        pass

    def __init_subclass__(cls, wrap_tm_accessors: bool = True, **kwargs: Any):
        if wrap_tm_accessors:
            cls.decoratate_tm_accessors()
        return super().__init_subclass__(**kwargs)

    @classmethod
    def decoratate_tm_accessors(cls) -> None:
        if cls._snapshot_accessors_wrapped:
            return

        @wraps(cls.__setattr__)
        def wrapper_setattr(self, key: str, val: Any, *, _old=cls.__setattr__) -> None:
            if key == "snapshot_for" and self._snapshots:
                tmp = self._snapshots[0]
                counter = 1
                old_data = {k: v for k, v in self.data.items() if k in self.managed}
                data = {}
                data.update(tmp.data)
                len_snapshots = len(self._snapshots)
                while counter < len_snapshots and tmp.snapshot_for <= self.snapshot_for:
                    tmp = self._snapshots[counter]
                    data.update(tmp.data)
                    counter += 1
                data.update(old_data)
                self.data = data

            if isinstance(field := cls.__dict__.get(key), TMField):
                self.managed.add(key)
                name = field.name if field.name else key
                self.data[name] = field.serializer(val)
                return
            else:
                _old(key, val)

        cls.__setattr__ = wrapper_setattr  # type: ignore

        old_getattr = getattr(cls, "__getattr__", None)
        if old_getattr:  # noqa: SIM108
            gwrapper: Any = wraps(old_getattr)
        else:
            gwrapper = nullcontext()
            old_getattr = getattr

        @gwrapper
        def wrapper_getattr(self, key: str, *, _old=old_getattr) -> Any:
            if isinstance(field := cls.__dict__.get(key), TMField):
                name = field.name if field.name else key
                return field.deserializer(self.data[name])
            else:
                return _old(key)

        cls.__getattr__ = wrapper_getattr  # type: ignore

        def wrapper_delattr(self, key: str, *, _old=cls.__delattr__) -> None:
            if isinstance(field := cls.__dict__.get(key), TMField):
                name = field.name if field.name else key
                self.data.pop(name, None)
            else:
                _old(key)

        cls.__delattr__ = wrapper_delattr  # type: ignore
        cls._snapshot_accessors_wrapped = True
