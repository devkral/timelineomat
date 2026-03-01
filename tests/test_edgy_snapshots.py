from dataclasses import asdict, dataclass, field
from datetime import datetime as dt
from typing import Any

import edgy
import pytest
from edgy import Registry
from edgy.testing.client import DatabaseTestClient

from timelineomat import BaseTMSnapshot, SnapshotType, extract_snapshot_data

database = DatabaseTestClient("sqlite:///test_db.sqlite", drop_database=True)
models = Registry(database=edgy.Database(database, force_rollback=True))

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    # this creates and drops the database
    async with database:
        await models.create_all()
        yield
        await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    # this rolls back
    async with models:
        yield


class SnapshotImplementation(edgy.Model):
    data = edgy.fields.JSONField(default=dict)
    snapshot_for: dt = edgy.fields.DateTimeField()
    snapshot_type = edgy.fields.SmallIntegerField(gte=0, lt=2)
    content_specifier = edgy.fields.CharField(max_length=20)

    class Meta:
        registry = models


# Note: not an edgy model
@dataclass(kw_only=True)
class Snapshot(BaseTMSnapshot):
    snapshot_for: dt
    data: dict[str, Any] = field(default_factory=dict, init=False)
    # managed is extra
    managed: set[str] = field(default_factory=set, init=False)
    snapshot_type: SnapshotType

    def __post_init__(self, **kwargs):
        # fix data
        for attr_name in list(self.__dict__):
            attr_value = self.__dict__[attr_name]
            if isinstance(field := type(self).__dict__.get(attr_name), TMField):
                del self.__dict__[attr_name]
                if attr_value is not field:
                    self.data[attr_name] = field.serializer(attr_value)

    @classmethod
    async def get_snapshot_impl(cls, *, content_specifier, after=None, before=None, start_snapshot=None):
        snapshots = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data = None
        current_snapshot_data = {}
        snapshot_type = SnapshotType.temporary
        query = SnapshotImplementation.query.filter(content_specifier=content_specifier).order_by("snapshot_for")
        if before is not None:
            query = query.filter(snapshot_for__lt=before)
        if after is None:
            # start_snapshot is None
            start_snapshot = await query.filter(snapshot_type="full").last()
        if start_snapshot is not None:
            query = query.filter(snapshot_for__gt=start_snapshot)
        for snap in await query:
            extracted, timepoint, snap_type = extract_snapshot_data(snap, fallback_tz=cls.snapshot_fallback_tz)
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

    @classmethod
    def get_snapshots(cls, **kwargs):
        assert kwargs.get("content_specifier") is None
        # content_specifier = cls.__name__
        return super().get_snapshots(**kwargs)

    async def save(self):
        data, snapshot_for, snap_type = extract_snapshot_data(self, fallback_tz=self.snapshot_fallback_tz)

        return await SnapshotImplementation(
            data=data, snapshot_for=snapshot_for, snapshot_type=snap_type, content_specifier=type(self).__name__
        ).save()


@dataclass(kw_only=True)
class SnapshotSubtype1(Snapshot):
    stringified: str = TMField(serializer=str)  # type: ignore
    stringified_int: int = TMField(serializer=str, deserializer=int)  # type: ignore


@dataclass(kw_only=True)
class SnapshotSubtype2(Snapshot):
    stringified2: str = TMField(serializer=str)  # type: ignore
    stringified_int2: int = TMField(serializer=str, deserializer=int)  # type: ignore


async def test_violations():
    with pytest.raises(ValueError):
        await SnapshotImplementation.query.create(
            snapshot_type=30, snapshot_for=dt(year=2025, month=1, day=2), content_specifier="foo"
        )
    with pytest.raises(ValueError):
        await SnapshotImplementation.query.create(
            snapshot_type=SnapshotType.full, snapshot_for=dt(year=2025, month=1, day=2)
        )


async def test_bad_invovation():
    with pytest.raises(TypeError):
        SnapshotSubtype1.get_snapshots("foo")
    with pytest.raises(AssertionError):
        SnapshotSubtype1.get_snapshots(content_specifier="foo")


sample_snapshots_sub1 = [
    {
        "snapshot_for": dt(year=2025, month=1, day=2),
        "snapshot_type": SnapshotType.full,
        "stringified": 1,
        "stringified_int": 7,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=2),
        "snapshot_type": SnapshotType.sparse,
        "stringified_int": 8,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=3),
        "snapshot_type": SnapshotType.sparse,
        "stringified": 9,
    },
    {
        "snapshot_for": dt(year=2025, month=1, day=4),
        "snapshot_type": SnapshotType.full,
        "stringified": 111,
        "stringified_int": 10,
    },
]


async def test_basic():
    for i in sample_snapshots_sub1:
        impl = await SnapshotSubtype1(**i).save()
        assert impl.data
    assert await SnapshotSubtype2.get_snapshots() is None
    real = await SnapshotSubtype1.get_snapshots()
    assert real is not None
    assert real.snapshot_type == SnapshotType.full
    assert real.snapshot_for == dt(year=2025, month=1, day=4)
    assert len(real._snapshots) == 1

    combined = await SnapshotSubtype1.get_snapshots(before=dt(year=2025, month=1, day=4))
    assert combined is not None
    assert combined.snapshot_type == SnapshotType.sparse
    assert combined.snapshot_for == dt(year=2025, month=1, day=3)
    assert len(combined._snapshots) == 3


async def test_set_date():
    for i in sample_snapshots_sub1:
        await SnapshotSubtype1(**i).save()

    combined = await SnapshotSubtype1.get_snapshots(before=dt(year=2025, month=1, day=4))
    assert combined is not None
    assert combined.stringified == "9"
    combined.snapshot_for = dt(year=2025, month=1, day=2)
    assert combined.stringified == "1"
