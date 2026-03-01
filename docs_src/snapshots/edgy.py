from dataclasses import dataclass, field
from datetime import datetime as dt
from typing import Any

import edgy
import pytest

from timelineomat import BaseTMSnapshot, SnapshotType, TMField, extract_snapshot_data

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


class SnapshotSubtype1(Snapshot):
    stringified: str = TMField(serializer=str)  # type: ignore
    stringified_int: int = TMField(serializer=str, deserializer=int)  # type: ignore
