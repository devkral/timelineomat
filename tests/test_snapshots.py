from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import asdict, dataclass, field
from datetime import datetime as dt
from typing import Any, Self

import pytest

from timelineomat import BaseTMSnapshot, SnapshotType, extract_snapshot_data

pytestmark = pytest.mark.anyio

obj1 = object()
obj2 = object()
obj3 = object()
obj4 = object()


async def asyncify(inp):
    return inp


@dataclass(kw_only=True)
class DummySnapshot(BaseTMSnapshot):
    snapshot_for: dt = field(init=False)
    content_specifier: str = field(init=False)
    data: dict[str, Any] = field(init=False)
    snapshot_type: SnapshotType = field(init=False)

    stay_same: Any
    stringified: str
    stringified_int: int

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
        full_data["stringified_int"] = int(full_data["stringified_int"])
        full_data["stringified"] = str(full_data["stringified"])
        full_data.pop("content_specifier", None)
        full_data.pop("snapshot_for", None)
        return super().deserialize_snapshot(
            full_data,
            data=data,
            snapshot_for=snapshot_for,
            snapshot_type=snapshot_type,
            content_specifier=content_specifier,
        )

    def save(self):
        full_data = asdict(self)
        full_data["stringified_int"] = str(full_data["stringified_int"])
        for key in list(full_data.keys()):
            if key not in self.updated_attrs:
                del full_data[key]
        return full_data

    @classmethod
    def get_snapshots_impl(cls, *, content_specifier, after, before, start_snapshot, shall_async=False):
        snapshots = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data = None
        for snap in globals()[content_specifier]:
            extracted, timepoint, snap_type = extract_snapshot_data(snap, fallback_tz=cls.snapshot_fallback_tz)
            if before is not None and timepoint >= before:
                break
            if after is not None and timepoint < after:
                if snap_type == SnapshotType.full:
                    first_snapshot_data = extracted
                    first_snapshot_data["snapshot_for"] = timepoint
                elif first_snapshot_data is not None:
                    first_snapshot_data.update(extracted)
                    first_snapshot_data["snapshot_for"] = timepoint
                continue
            if snap_type != SnapshotType.full and not snapshots and first_snapshot_data is None:
                raise ValueError("No full snapshot found")
            if not snapshots and first_snapshot_data is not None:
                if snap_type != SnapshotType.full:
                    first_snapshot_data["snapshot_type"] = SnapshotType.temporary
                    first_snapshot_data["snapshot_for"] = after or timepoint
                    assert "snapshot_type" in first_snapshot_data
                    snapshots.append(first_snapshot_data)

                first_snapshot_data = None
            # start from the last full snapshot if both are None
            if snap_type == SnapshotType.full and before is None and after is None:
                snapshots.clear()
                first_snapshot_data = None
            assert "snapshot_type" in snap
            snapshots.append(snap)
        if first_snapshot_data is not None:
            first_snapshot_data["snapshot_type"] = SnapshotType.temporary
            snapshots.insert(0, first_snapshot_data)
        if shall_async:
            return asyncify(snapshots)
        return snapshots


@dataclass(kw_only=True)
class DummySnapshot2(DummySnapshot):
    @classmethod
    def get_snapshots(cls, **kwargs):
        return super().get_snapshots(**kwargs)

    @classmethod
    def process_snapshot_content_specifier(cls, content_specifier: str | None):
        return content_specifier or "dummy_snapshots"


dummy_snapshots = [
    {
        "snapshot_for": dt(year=2025, month=1, day=1),
        "snapshot_type": SnapshotType.full,
        "content_specifier": "DjangoContentType",
        "stay_same": obj1,
        "stringified": 1,
        "stringified_int": 8,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=2),
        "snapshot_type": SnapshotType.sparse,
        "content_specifier": "DjangoContentType",
        "stringified_int": 8,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=3),
        "snapshot_type": SnapshotType.sparse,
        "content_specifier": "DjangoContentType",
        "stringified": 9,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=4),
        "snapshot_type": SnapshotType.full,
        "content_specifier": "DjangoContentType",
        "stay_same": obj2,
        "stringified": 111,
        "stringified_int": 10,
    },
]

dummy_snapshots2 = [
    *dummy_snapshots,
    {
        "snapshot_for": dt(year=2025, month=1, day=5),
        "snapshot_type": SnapshotType.sparse,
        "content_specifier": "DjangoContentType",
        "stringified": 2,
    },
]

dummy_snapshots_empty: list[Any] = []


def test_invalid_invocation():
    with pytest.raises(TypeError):
        DummySnapshot.get_snapshots(",", "foo")
    with pytest.raises(TypeError):
        DummySnapshot.get_snapshots("foo", content_specifier="foo")


def test_invalid_start_snapshot():
    with pytest.raises(ValueError):
        snapshot = DummySnapshot(
            stay_same=obj1,
            stringified=1,
            stringified_int=8,
        )
        snapshot.data = {}
        snapshot.snapshot_for = dt(year=2025, month=1, day=1)
        snapshot.snapshot_type = SnapshotType.sparse
        snapshot.content_specifier = "DjangoContentType"
        DummySnapshot.get_snapshots("dummy_snapshots", start_snapshot=snapshot)

    with pytest.raises(ValueError):
        DummySnapshot.get_snapshots(
            "dummy_snapshots",
            start_snapshot={
                "snapshot_for": dt(year=2025, month=1, day=1),
                "snapshot_type": SnapshotType.sparse,
                "content_specifier": "DjangoContentType",
                "stay_same": obj1,
                "stringified": 1,
                "stringified_int": 8,
            },
        )


def test_overwrite():
    assert isinstance(next(iter(DummySnapshot2.get_snapshots()))[1], DummySnapshot2)
    assert isinstance(next(iter(DummySnapshot2.get_snapshots(content_specifier="dummy_snapshots")))[1], DummySnapshot2)
    timeline = DummySnapshot2.get_snapshots(content_specifier="dummy_snapshots_empty")
    assert timeline[dt(year=2025, month=1, day=1)] is None
    assert list(timeline) == []


def test_empty():
    assert list(DummySnapshot.get_snapshots("dummy_snapshots_empty")) == []


def test_snapshot_unranged():
    timeline = DummySnapshot.get_snapshots("dummy_snapshots")
    assert len(timeline) == 1
    snap = timeline[None]
    assert snap.stringified_int == 10
    assert snap.stringified == "111"
    assert snap.stay_same is obj2
    assert snap.snapshot_type == SnapshotType.full
    assert snap.snapshot_for == dt(year=2025, month=1, day=4)


async def test_async_arg():
    timeline = await DummySnapshot.get_snapshots("dummy_snapshots", shall_async=True)
    snap = timeline[None]
    assert len(timeline) == 1
    assert snap.stringified_int == 10
    assert snap.stringified == "111"
    assert snap.stay_same is obj2
    assert snap.snapshot_type == SnapshotType.full
    assert snap.snapshot_for == dt(year=2025, month=1, day=4)


def test_snapshot_before():
    snap = DummySnapshot.get_snapshots("dummy_snapshots", before=dt(year=2025, month=1, day=4))[None]
    assert snap.stringified_int == 8
    assert snap.stringified == "9"
    assert snap.stay_same is obj1
    assert snap.snapshot_type == SnapshotType.sparse


def test_snapshot_before_all():
    snap = DummySnapshot.get_snapshots("dummy_snapshots", before=dt(year=2025, month=1, day=1))[None]
    assert snap is None


def test_snapshot_after_all_full():
    timeline = DummySnapshot.get_snapshots("dummy_snapshots", after=dt(year=2025, month=1, day=10))
    assert len(timeline) == 1
    snap = timeline[None]
    assert snap is not None
    assert snap.snapshot_for == dt(year=2025, month=1, day=4)
    assert snap.snapshot_type == SnapshotType.temporary


def test_snapshot_after_all_sparse():
    timeline = DummySnapshot.get_snapshots("dummy_snapshots2", after=dt(year=2025, month=1, day=10))
    assert len(timeline) == 1
    snap = timeline[None]
    assert snap is not None
    assert snap.snapshot_for == dt(year=2025, month=1, day=5)
    assert snap.snapshot_type == SnapshotType.temporary
