from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Generator, Iterator, MutableMapping, Sequence
from datetime import datetime as dt
from datetime import timedelta as td
from enum import IntEnum
from functools import cached_property
from inspect import isawaitable
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
    Protocol,
    Self,
    TypedDict,
    TypeVar,
    cast,
    overload,
)


class SnapshotType(IntEnum):
    sparse = 0
    full = 1
    temporary = 2


SnapshotTypeVariant = SnapshotType | Literal["sparse", "full", "temporary"]


class SnapshotObject(Protocol):
    data: MutableMapping[str, Any] | dict[str, Any]
    snapshot_for: dt | int | str
    snapshot_type: SnapshotTypeVariant


class SnapshotDict(TypedDict):
    data: MutableMapping[str, Any] | dict[str, Any]
    snapshot_for: dt | int | str
    snapshot_type: SnapshotType


SnapshotDict.__required_keys__ = frozenset(("snapshot_for", "snapshot_type"))


SnapshotTimelineEntry = SnapshotObject | SnapshotDict


def parse_dt(inp: dt | int | str, *, fallback_tz: Any = None) -> dt:
    if isinstance(inp, str):
        inp = dt.fromisoformat(inp)
    elif isinstance(inp, int):
        inp = dt.fromtimestamp(inp)
    if inp.tzinfo is None and fallback_tz is not None:
        inp = inp.replace(tzinfo=fallback_tz)
    return inp


def extract_snapshot_data(
    entry: SnapshotTimelineEntry, *, fallback_tz: Any = None
) -> tuple[dict[str, Any], dt, SnapshotType]:
    if isinstance(entry, dict):
        # data can be flat or in data when a dict
        if "data" in entry:
            data: dict[str, Any] = {**entry["data"]}
            snapshot_type: SnapshotTypeVariant = entry["snapshot_type"]
            snapshot_for = entry["snapshot_for"]
        else:
            data = {**entry}
            snapshot_type = data.pop("snapshot_type")
            snapshot_for = data.pop("snapshot_for")
    else:
        # data must be in "data" attribute
        data = {**entry.data}
        snapshot_for = entry.snapshot_for
        snapshot_type = entry.snapshot_type

    # int or stringified int
    if isinstance(snapshot_type, str):
        if snapshot_type in SnapshotType.__members__:
            snapshot_type = cast(SnapshotType, getattr(SnapshotType, snapshot_type))
        elif snapshot_type.isdecimal():
            snapshot_type = SnapshotType(int(snapshot_type))
        else:
            raise ValueError("Invalid snapshot_type.")
    elif isinstance(snapshot_type, int):
        snapshot_type = SnapshotType(snapshot_type)
    elif not isinstance(snapshot_type, SnapshotType):
        raise ValueError("Invalid snapshot_type.")
    return (data, parse_dt(snapshot_for, fallback_tz=fallback_tz), snapshot_type)


_SnapshotInstanceType = TypeVar("_SnapshotInstanceType", bound="BaseTMSnapshot")


class TMSnapshotTimeline(Generic[_SnapshotInstanceType]):
    _snapshots: list[_SnapshotInstanceType]
    klass: type[_SnapshotInstanceType]

    def __init__(
        self, klass: type[_SnapshotInstanceType], snapshots: Sequence[SnapshotTimelineEntry], content_specifier: str, /
    ) -> None:
        self.klass = klass
        self._snapshots = []
        data: dict[str, Any] | None = None
        for snapshot in snapshots:
            extracted, timepoint, snapshot_type = extract_snapshot_data(
                snapshot, fallback_tz=klass.snapshot_fallback_tz
            )
            if snapshot_type == SnapshotType.full or snapshot_type == SnapshotType.temporary:
                data = extracted
            elif data is not None:
                data.update(extracted)
            else:
                raise ValueError("Must start with a full or temporary snapshot")
            assert isinstance(data, MutableMapping)
            self._snapshots.append(
                klass.deserialize_snapshot(
                    # manipulation will lead to hard to debug issues otherwise
                    data.copy(),
                    data=extracted,
                    snapshot_for=timepoint,
                    snapshot_type=snapshot_type,
                    content_specifier=content_specifier,
                )
            )

    @classmethod
    async def resolve_async(
        cls,
        klass: type[_SnapshotInstanceType],
        snapshots: Awaitable[Sequence[SnapshotTimelineEntry]],
        content_specifier: str,
    ) -> Self:
        sn = await snapshots
        return cls(klass, sn, content_specifier)

    def __getitem__(self, timestamp: dt | int | str | None, /) -> _SnapshotInstanceType | None:
        last_item: _SnapshotInstanceType | None = None
        # fake, it will be always set to non-none wnen last_item is not None
        last_item_sanitized_timestamp: dt = cast(dt, None)
        sanitized_timestamp = (
            parse_dt(timestamp, fallback_tz=self.klass.snapshot_fallback_tz) if timestamp is not None else None
        )
        for item in self._snapshots:
            item_sanitized_timestamp = parse_dt(item.snapshot_for, fallback_tz=self.klass.snapshot_fallback_tz)
            if (
                last_item is not None
                and sanitized_timestamp is not None
                and last_item_sanitized_timestamp < sanitized_timestamp
                and item_sanitized_timestamp < sanitized_timestamp
            ):
                return last_item
            last_item = item
            last_item_sanitized_timestamp = item_sanitized_timestamp
        return last_item

    def iterate(
        self, *, step: td | None = None, stop: dt | None = None
    ) -> Generator[tuple[dt, _SnapshotInstanceType], None, None]:
        counter: dt = cast(dt, None)
        pos_item: int = 0
        next_timestamp: None | dt = None
        len_snapshots: int = len(self._snapshots)
        if not len_snapshots:
            return
        # test before ensures len_snapshots > 0
        max_pos_snapshots: int = len_snapshots - 1
        while True:
            item = self._snapshots[pos_item]
            if counter is None:
                counter = parse_dt(item.snapshot_for, fallback_tz=self.klass.snapshot_fallback_tz)
            if stop is not None and counter > stop:
                return
            yield (counter, item)
            if step is not None:
                counter += step
                if pos_item < max_pos_snapshots:
                    if next_timestamp is None:
                        next_timestamp = parse_dt(item.snapshot_for, fallback_tz=self.klass.snapshot_fallback_tz)
                    if next_timestamp <= counter:
                        pos_item += 1
                        next_timestamp = None
            else:
                if pos_item < max_pos_snapshots:
                    pos_item += 1
                else:
                    return

    def __iter__(self) -> Iterator[tuple[dt, _SnapshotInstanceType]]:
        return self.iterate()

    def __len__(self):
        return len(self._snapshots)


_SnapshotImplReturnType = TypeVar("_SnapshotImplReturnType", covariant=True)
_SnapshotImplKwargs = TypeVar("_SnapshotImplKwargs")


class _BaseSnapshotImplType(Protocol[_SnapshotImplReturnType]):
    @classmethod
    @abstractmethod
    def get_snapshots_impl(
        cls,
        *,
        content_specifier: str,
        after: dt | None,
        before: dt | None,
        start_snapshot: None | SnapshotTimelineEntry,
    ) -> _SnapshotImplReturnType: ...


_SyncSnapshotImplType = _BaseSnapshotImplType[Sequence[_SnapshotInstanceType]]
_AsyncSnapshotImplType = _BaseSnapshotImplType[Awaitable[Sequence[_SnapshotInstanceType]]]

if TYPE_CHECKING:

    class _BaseTMSnapshot(_BaseSnapshotImplType, SnapshotObject, ABC):
        pass

else:
    # otherwise we end with an inconsistent inheritance order e.g. with edgy

    class _BaseTMSnapshot(_BaseSnapshotImplType, ABC):  # noqa
        pass


class BaseTMSnapshot(_BaseTMSnapshot):
    snapshot_fallback_tz: ClassVar[Any] = None
    snapshot_attrs_as_kwargs: ClassVar[bool] = False
    content_specifier: str

    @classmethod
    def deserialize_snapshot(
        cls,
        full_data: MutableMapping[str, Any],
        *,
        data: MutableMapping[str, Any],
        snapshot_for: dt,
        snapshot_type: SnapshotType,
        content_specifier: str,
    ) -> Self:
        snapshot_obj = cls(**full_data)
        snapshot_obj.data = data
        snapshot_obj.snapshot_type = snapshot_type
        snapshot_obj.snapshot_for = snapshot_for
        snapshot_obj.content_specifier = content_specifier
        return snapshot_obj

    @classmethod
    def process_snapshot_content_specifier(cls, content_specifier: str | None) -> str:
        """
        For customizing the naming logic and processing, like escaping.

        The result is used for comparations.

        By default None and "" are handled equally but this logic is overwritable.
        """
        return content_specifier or cls.__name__

    @overload
    @classmethod
    def get_snapshots(
        cls: type[_AsyncSnapshotImplType],
        content_specifier: str | None = None,
        *,
        after: dt | None = None,
        before: dt | None = None,
        start_snapshot: None | SnapshotTimelineEntry = None,
        **kwargs: _SnapshotImplKwargs,
    ) -> Awaitable[TMSnapshotTimeline[_SnapshotInstanceType]]: ...

    @overload
    @classmethod
    def get_snapshots(
        cls: type[_SyncSnapshotImplType],
        content_specifier: str | None = None,
        *,
        after: dt | None = None,
        before: dt | None = None,
        start_snapshot: None | SnapshotTimelineEntry = None,
        **kwargs: _SnapshotImplKwargs,
    ) -> TMSnapshotTimeline[_SnapshotInstanceType]: ...

    @classmethod
    def get_snapshots(
        cls: type[_AsyncSnapshotImplType | _SyncSnapshotImplType],
        content_specifier: str | None = None,
        *,
        after: dt | None = None,
        before: dt | None = None,
        start_snapshot: None | SnapshotTimelineEntry = None,
        **kwargs: _SnapshotImplKwargs,
    ) -> TMSnapshotTimeline[_SnapshotInstanceType] | Awaitable[TMSnapshotTimeline[_SnapshotInstanceType]]:
        content_specifier = cast(BaseTMSnapshot, cls).process_snapshot_content_specifier(content_specifier)
        if start_snapshot is not None:
            snap_for, snap_type = extract_snapshot_data(start_snapshot)[1:]
            if snap_type not in {
                SnapshotType.full,
                SnapshotType.temporary,
            }:
                raise ValueError("Invalid `start_snapshot`. Not a `temporary` or `full` snapshot.")
            # the start snapshot ensures that after is set
            if after is None or after < snap_for:
                after = snap_for
            if isinstance(start_snapshot, dict):
                content_specifier_start = start_snapshot.get("content_specifier")
            else:
                content_specifier_start = getattr(start_snapshot, "content_specifier", None)
            # if found compare against the model type of start_snapshot
            if content_specifier_start:
                assert content_specifier_start == content_specifier, (
                    "`start_snapshot` and `content_specifier` doesn't match."
                )
        result = cls.get_snapshots_impl(
            content_specifier=content_specifier, after=after, before=before, start_snapshot=start_snapshot, **kwargs
        )
        if isawaitable(result):
            return TMSnapshotTimeline.resolve_async(cast(type[_SnapshotInstanceType], cls), result, content_specifier)
        else:
            return TMSnapshotTimeline(cast(type[_SnapshotInstanceType], cls), result, content_specifier)

    @cached_property
    def updated_attrs(self) -> set[str]:
        """
        Return set with updated attrs.

        Use `self.__dict__.pop("updated_attrs", None)` to reset.
        """
        return set()

    @property
    def object_not_updated(self) -> bool:
        """Object was not touched and no relevant attributes were changed."""
        return "updated_attrs" not in self.__dict__

    def is_attr_change_update(self, name: str, value: Any) -> bool:
        """Update to limit to actual fields."""
        if "data" not in self.__dict__:
            # we are in init
            return False
        return name not in self.data or self.data[name] != value

    def __setattr__(self, name: str, value: Any):
        if self.is_attr_change_update(name, value):
            self.updated_attrs.add(name)
        elif "updated_attrs" in self.__dict__:
            self.updated_attrs.discard(name)
        return super().__setattr__(name, value)

    def __delattr__(self, name: str):
        if name in self.data:
            self.updated_attrs.add(name)
        elif "updated_attrs" in self.__dict__:
            self.updated_attrs.discard(name)
        return super().__delattr__(name)
