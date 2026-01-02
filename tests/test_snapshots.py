from dataclasses import dataclass, field
from datetime import datetime as dt
from typing import Any

from timelineomat import BaseTMSnapshot, SnapshotType, TMField, extract_snapshot_data

obj1 = object()
obj2 = object()
obj3 = object()
obj4 = object()


@dataclass(kw_only=True)
class DummySnapshot(BaseTMSnapshot):
    snapshot_for: dt
    model_type: str
    data: dict[str, Any] = field(default_factory=dict, init=False)
    managed: set[str] = field(default_factory=set, init=False)
    snapshot_type: SnapshotType

    stay_same: Any = TMField()
    stringified: Any = TMField(serializer=str)
    stringified_int: Any = TMField(serializer=str, deserializer=int)

    @classmethod
    def get_snapshot_impl(cls, *, model_type, after=None, before=None, start_snapshot=None):
        snapshots = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data = None
        current_snapshot_data = {}
        snapshot_type = SnapshotType.temporary
        for snap in globals()[model_type]:
            extracted, timepoint, snap_type = extract_snapshot_data(snap)
            if before is not None and timepoint >= before:
                break
            if after is not None and timepoint < after:
                if snap_type == SnapshotType.full:
                    current_snapshot_data = first_snapshot_data = extracted
                    first_snapshot_data["snapshot_for"] = current_snapshot_data["snapshot_for"] = timepoint
                elif first_snapshot_data is not None:
                    current_snapshot_data.update(extracted)
                    first_snapshot_data.update(extracted)
                    first_snapshot_data["snapshot_for"] = current_snapshot_data["snapshot_for"] = timepoint
                continue
            if snap_type != SnapshotType.full and (not snapshots or first_snapshot_data is not None):
                raise ValueError("No full snapshot found")
            if snap_type == SnapshotType.full:
                current_snapshot_data.clear()
            current_snapshot_data.update(extracted)
            current_snapshot_data["snapshot_for"] = timepoint
            snapshot_type = snap_type
            if not snapshots and first_snapshot_data is not None:
                if snap_type != SnapshotType.full:
                    first_snapshot_data["snapshot_type"] = SnapshotType.temporary
                    first_snapshot_data["snapshot_for"] = after or timepoint
                    snapshots.append(first_snapshot_data)

                first_snapshot_data = None
            # start from the last full snapshot
            if snap_type == SnapshotType.full and before is None and after is None:
                snapshots.clear()
                first_snapshot_data = None
            snapshots.append(snap)
        if first_snapshot_data is not None:
            snapshots.insert(0, first_snapshot_data)
        if not snapshots:
            return None
        instance = cls(
            snapshot_type=snapshot_type,
            **current_snapshot_data,
        )
        instance._snapshots = snapshots
        return instance


dummy_snapshots = [
    DummySnapshot(
        snapshot_for=dt(year=2025, month=1, day=1),
        snapshot_type=SnapshotType.full,
        model_type="DjangoContentType",
        stay_same=obj1,
        stringified=1,
        stringified_int=8,
    ),
    {
        "snapshot_for": dt(year=2025, month=1, day=2),
        "snapshot_type": SnapshotType.sparse,
        "model_type": "DjangoContentType",
        "stringified_int": 8,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=3),
        "snapshot_type": SnapshotType.sparse,
        "model_type": "DjangoContentType",
        "stringified": 9,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=4),
        "snapshot_type": SnapshotType.full,
        "model_type": "DjangoContentType",
        "stay_same": obj2,
        "stringified": 111,
        "stringified_int": 10,
    },
]

dummy_snapshots_empty: list[Any] = []


def test_empty():
    assert DummySnapshot.get_snapshot("dummy_snapshots_empty") is None


def test_snapshot_unranged():
    snap = DummySnapshot.get_snapshot("dummy_snapshots")
    assert snap.stringified_int == 10
    assert snap.stringified == "111"
    assert snap.stay_same is obj2
    assert snap.snapshot_type == SnapshotType.full
    assert snap.snapshot_for == dt(year=2025, month=1, day=4)
    assert len(snap._snapshots) == 1


def test_snapshot_before():
    snap = DummySnapshot.get_snapshot("dummy_snapshots", before=dt(year=2025, month=1, day=4))
    assert snap.stringified_int == 8
    assert snap.stringified == "9"
    assert snap.stay_same is obj1
    assert snap.snapshot_type == SnapshotType.sparse


def test_snapshot_before_all():
    snap = DummySnapshot.get_snapshot("dummy_snapshots", before=dt(year=2025, month=1, day=1))
    assert snap is None


def test_snapshot_after_all():
    snap = DummySnapshot.get_snapshot("dummy_snapshots", after=dt(year=2025, month=1, day=10))
    assert snap is not None
    assert snap.snapshot_for == dt(year=2025, month=1, day=4)
    assert len(snap._snapshots) == 1
