from collections.abc import MutableMapping
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Annotated, Any, Self

import edgy
import pytest
from edgy import Registry
from edgy.testing.client import DatabaseTestClient
from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer, computed_field

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
    snapshot_for: dt = edgy.fields.DateTimeField(primary_key=True)
    content_specifier = edgy.fields.CharField(max_length=50, primary_key=True)
    # only 0, 1
    snapshot_type = edgy.fields.SmallIntegerField(gte=0, lt=2)

    class Meta:
        registry = models


# Note: not an edgy model
class Snapshot(BaseTMSnapshot, BaseModel):
    data: MutableMapping[str, Any] = Field(init=False, default_factory=dict)
    snapshot_for: dt
    snapshot_type: SnapshotType
    _loaded: bool = False

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
        # snapshot_obj.content_specifier = content_specifier
        snapshot_obj._loaded = True
        return snapshot_obj

    @classmethod
    async def get_snapshots_impl(cls, *, content_specifier, after=None, before=None, start_snapshot=None):
        snapshots = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data = None
        query = SnapshotImplementation.query.filter(content_specifier=content_specifier).order_by("snapshot_for")

        if before is not None:
            query = query.filter(snapshot_for__lt=before)
        if after is None:
            # start_snapshot is None
            assert start_snapshot is None
            starting_snapshot = await query.filter(snapshot_type=SnapshotType.full).last()
            if starting_snapshot is not None:
                snapshots.append(starting_snapshot)
                after = extract_snapshot_data(starting_snapshot)[1]
                query = query.filter(snapshot_for__gt=after)
            snapshots_list = await query
        elif start_snapshot is not None:
            query = query.filter(snapshot_for__gt=after)
            snapshots_list = await query
        else:
            starting_snapshot = await query.filter(snapshot_type=SnapshotType.full, snapshot_for__lt=after).last()
            if starting_snapshot is not None:
                query = query.filter(snapshot_for__gt=starting_snapshot.snapshot_for)
                snapshots_list = [starting_snapshot, *(await query)]
            else:
                snapshots_list = await query
            # otherwise just load everything and filter manually
        for snap in snapshots_list:
            extracted, timepoint, snap_type = extract_snapshot_data(snap, fallback_tz=cls.snapshot_fallback_tz)
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
                    snapshots.append(first_snapshot_data)

                first_snapshot_data = None
            snapshots.append(snap)
        if first_snapshot_data is not None:
            first_snapshot_data["snapshot_type"] = SnapshotType.temporary
            snapshots.insert(0, first_snapshot_data)
        return snapshots

    @classmethod
    def get_snapshots(cls, **kwargs):
        assert kwargs.get("content_specifier") is None
        # content_specifier = cls.__name__
        return super().get_snapshots(**kwargs)

    async def save(self):
        snapshot_for, snap_type = extract_snapshot_data(self, fallback_tz=self.snapshot_fallback_tz)[1:]
        if snap_type == SnapshotType.temporary:
            raise ValueError("Cannot save a temporary Snapshot.")
        if self._loaded and not self.object_not_updated:
            return
        data = self.model_dump(include=self.updated_attrs if self._loaded else None, exclude_none=True)
        impl = await SnapshotImplementation(
            data=data, snapshot_for=snapshot_for, snapshot_type=snap_type, content_specifier=type(self).__name__
        ).save()
        self.data = data
        self.__dict__.pop("updated_attrs", None)
        self._loaded = True
        return impl


def stringify(x):
    return str(x)


class SnapshotSubtype1(Snapshot):
    stringified: Annotated[str | None, BeforeValidator(stringify)] = None
    stringified_int: Annotated[int | None, PlainSerializer(stringify)] = None

    @computed_field
    def content_specifier(self) -> str:
        return type(self).__name__

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
        if full_data.get("stringified_int") is not None:
            full_data["stringified_int"] = int(full_data["stringified_int"])
        if full_data.get("stringified") is not None:
            full_data["stringified"] = str(full_data["stringified"])
        return super().deserialize_snapshot(
            full_data,
            data=data,
            snapshot_for=snapshot_for,
            snapshot_type=snapshot_type,
            content_specifier=content_specifier,
        )


class SnapshotForIdObjects(Snapshot):
    id: int
    stringified2: Annotated[str | None, BeforeValidator(stringify)] = None
    stringified_int2: Annotated[int | None, PlainSerializer(stringify)] = None

    @computed_field
    def content_specifier(self) -> str:
        return f"{type(self).__name__}:{self.id}"

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
        if full_data.get("stringified_int2") is not None:
            full_data["stringified_int2"] = int(full_data["stringified_int2"])
        if full_data.get("stringified2") is not None:
            full_data["stringified2"] = str(full_data["stringified2"])
        return super().deserialize_snapshot(
            full_data,
            data=data,
            snapshot_for=snapshot_for,
            snapshot_type=snapshot_type,
            content_specifier=content_specifier,
        )


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
        "snapshot_for": dt(year=2025, month=1, day=2, hour=2),
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
    {
        "snapshot_for": dt(year=2025, month=1, day=5),
        "snapshot_type": SnapshotType.sparse,
        "stringified": 11,
    },
]


async def test_basic():
    for i in sample_snapshots_sub1:
        impl = await SnapshotSubtype1.model_validate(i, strict=False).save()
        assert impl.data
    tl = await SnapshotForIdObjects.get_snapshots()
    assert len(tl) == 0
    real = await SnapshotSubtype1.get_snapshots()
    assert len(real) == 2
    assert real[dt(year=2025, month=1, day=4)].snapshot_type == SnapshotType.full
    last_snap = real[dt(year=2025, month=1, day=5)]
    assert last_snap.snapshot_type == SnapshotType.sparse
    assert last_snap.snapshot_for == dt(year=2025, month=1, day=5)
    assert last_snap.stringified == "11"
    assert last_snap.stringified_int == 10
    after_last_snap = real[dt(year=2025, month=1, day=8)]
    assert after_last_snap.snapshot_type == SnapshotType.sparse
    assert after_last_snap.snapshot_for == dt(year=2025, month=1, day=5)
    assert after_last_snap.stringified == "11"
    assert after_last_snap.stringified_int == 10

    combined = await SnapshotSubtype1.get_snapshots(before=dt(year=2025, month=1, day=4))
    assert len(combined) == 3
    assert combined[dt(year=2025, month=1, day=3)] == combined[None]
    assert combined[dt(year=2025, month=1, day=3)].snapshot_type == SnapshotType.sparse
    assert combined[dt(year=2025, month=1, day=3)].stringified == "9"


async def test_get_all():
    for i in sample_snapshots_sub1:
        await SnapshotSubtype1.model_validate(i, strict=False).save()

    tl = await SnapshotSubtype1.get_snapshots(after=dt.min)
    assert len(tl) == len(sample_snapshots_sub1)
    assert len(list(tl.iterate(before=dt(year=2025, month=1, day=4)))) == 3
    assert len(list(tl.iterate(after=dt(year=2025, month=1, day=4)))) == 1
