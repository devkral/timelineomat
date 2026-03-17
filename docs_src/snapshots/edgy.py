from collections.abc import MutableMapping
from datetime import datetime as dt
from typing import Any, Self

import edgy
import pytest
from pydantic import BaseModel, Field, computed_field

from timelineomat import BaseTMSnapshot, SnapshotType, extract_snapshot_data

DB_URL = ...
models = edgy.Registry(database=DB_URL)

pytestmark = pytest.mark.anyio


class SnapshotImplementation(edgy.Model):
    data = edgy.fields.JSONField(default=dict)
    snapshot_for: dt = edgy.fields.DateTimeField()
    snapshot_type = edgy.fields.SmallIntegerField()
    # if you want to validate that no temporary snapshot_type is materialized
    # snapshot_type = edgy.fields.SmallIntegerField(gte=0, lt=2)
    content_specifier = edgy.fields.CharField(max_length=10)

    class Meta:
        registry = models


# note: not an edgy model
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


class SnapshotSubtype1(Snapshot):
    string_field: str
    int_field: int

    @computed_field
    def content_specifier(self) -> str:
        return type(self).__name__


class SnapshotForIdObjects(Snapshot):
    id: int
    other_type: Any

    @computed_field
    def content_specifier(self) -> str:
        return f"{type(self).__name__}:{self.id}"
