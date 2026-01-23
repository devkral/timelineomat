from abc import ABC, abstractmethod
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime as dt
from enum import IntEnum
from functools import wraps
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, Self, TypedDict, cast, dataclass_transform


class SnapshotType(IntEnum):
    sparse = 0
    full = 1
    temporary = 2


SnapshotTypeVariant = SnapshotType | Literal["sparse", "full", "temporary"]


@dataclass(frozen=True)
class TMField:
    name: str | None = None
    serializer: Callable[[Any], Any] = field(default=lambda x: x)
    deserializer: Callable[[Any], Any] = field(default=lambda x: x)


class SnapshotObject(Protocol):
    data: MutableMapping[str, Any] | dict[str, Any]
    snapshot_for: dt | int | str
    snapshot_type: SnapshotTypeVariant


class SnapshotDict(TypedDict):
    data: MutableMapping[str, Any] | dict[str, Any]
    snapshot_for: dt | int | str
    snapshot_type: SnapshotType


SnapshotTimelineEntry = SnapshotObject | SnapshotDict


def extract_snapshot_data(
    entry: SnapshotTimelineEntry,
) -> tuple[MutableMapping[str, Any], dt, SnapshotType]:
    if isinstance(entry, dict):
        data: MutableMapping[str, Any] = cast(Any, entry.copy())
        snap_type = data.pop("snapshot_type")
        snapshot_for = data.pop("snapshot_for")
    else:
        data = entry.data
        snapshot_for = entry.snapshot_for
        snap_type = entry.snapshot_type

    if isinstance(snap_type, str):
        snap_type = getattr(SnapshotType, snap_type)
    elif isinstance(snap_type, int):
        snap_type = SnapshotType(snap_type)
    else:
        assert isinstance(snap_type, SnapshotType)
    return (data, snapshot_for, snap_type)


if TYPE_CHECKING:

    class _BaseTMSnapshot(SnapshotObject, ABC):
        pass

else:
    # otherwise we end with an inconsistent inheritance order e.g. with edgy

    class _BaseTMSnapshot(ABC):  # noqa
        pass


@dataclass_transform(field_specifiers=(TMField,), kw_only_default=True)
class BaseTMSnapshot(_BaseTMSnapshot):
    model_type: str
    _snapshot_accessors_wrapped: ClassVar[bool] = False
    managed: set[str]
    _snapshots: list[SnapshotTimelineEntry] | None = None

    @classmethod
    @abstractmethod
    def get_snapshot_impl(
        cls,
        *,
        model_type: str,
        after: dt | None = None,
        before: dt | None = None,
        start_snapshot: None | SnapshotTimelineEntry = None,
    ) -> Self | None:
        pass

    @classmethod
    def get_snapshot(
        cls,
        model_type: str | None = None,
        *,
        after: dt | None = None,
        before: dt | None = None,
        start_snapshot: None | SnapshotTimelineEntry = None,
        **kwargs,
    ) -> Self | None:
        if start_snapshot is not None:
            snap_for, snap_type = extract_snapshot_data(start_snapshot)[1:]
            assert snap_type in {
                SnapshotType.full,
                SnapshotType.temporary,
            }
            # the start snapshot ensures that after is set
            if after is None or after < snap_for:
                after = snap_for
            if mtype := getattr(start_snapshot, "model_type", None):
                if not model_type:
                    mtype = model_type
                else:
                    assert mtype == model_type
                model_type = mtype
        assert model_type is not None, "Couldn't determine the model_type. Please provide it."
        return cls.get_snapshot_impl(
            model_type=model_type, after=after, before=before, start_snapshot=start_snapshot, **kwargs
        )

    def __init_subclass__(cls, wrap_tm_accessors: bool = True, **kwargs):
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
                # first update
                _old(self, key, val)
                snap_data, snap_snap_for, snap_type = extract_snapshot_data(self._snapshots[0])
                counter = 1
                old_data = {k: v for k, v in self.data.items() if k in self.managed}
                data: dict = {}
                data.update(snap_data)
                len_snapshots = len(self._snapshots)
                while counter < len_snapshots and snap_snap_for <= self.snapshot_for:
                    snap_data, snap_snap_for, snap_type = extract_snapshot_data(self._snapshots[counter])
                    if snap_type == SnapshotType.temporary or snap_type == SnapshotType.full:
                        data.clear()
                    data.update(snap_data)
                    counter += 1
                data.update(old_data)
                self.data = data
                if snap_type == SnapshotType.full:
                    _old(self, "snap_type", SnapshotType.full)
                else:
                    _old(self, "snap_type", SnapshotType.temporary)
                return

            if isinstance(field := cls.__dict__.get(key), TMField):
                self.managed.add(key)
                name = field.name if field.name else key
                self.data[name] = field.serializer(val)
                return
            else:
                _old(self, key, val)

        cls.__setattr__ = wrapper_setattr  # type: ignore

        old_getattr = getattr(cls, "__getattribute__", None)
        if old_getattr:  # noqa: SIM108
            gwrapper: Any = wraps(old_getattr)
        else:
            gwrapper = lambda x: x  # noqa
            old_getattr = object.__getattribute__

        @gwrapper
        def wrapper_getattribute(self, key: str, *, _old=old_getattr) -> Any:
            if isinstance(field := cls.__dict__.get(key), TMField):
                name = field.name if field.name else key
                return field.deserializer(self.data[name])
            else:
                return _old(self, key)

        cls.__getattribute__ = wrapper_getattribute  # type: ignore

        def wrapper_delattr(self, key: str, *, _old=cls.__delattr__) -> None:
            if isinstance(field := cls.__dict__.get(key), TMField):
                name = field.name if field.name else key
                self.data.pop(name, None)
            else:
                _old(self, key)

        cls.__delattr__ = wrapper_delattr  # type: ignore
        cls._snapshot_accessors_wrapped = True

    def put_cache(self, key: str, value: Any) -> None:
        if isinstance(field := type(self).__dict__.get(key), TMField):
            self.data[field.name or key] = field.serializer(value)
        else:
            raise IndexError(f'"{key}" is not a TMField.')
