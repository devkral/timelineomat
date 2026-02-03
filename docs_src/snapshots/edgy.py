from datetime import datetime as dt

import edgy
import pytest

from timelineomat import BaseTMSnapshot, SnapshotType, TMField, extract_snapshot_data

models = edgy.Registry(database=DB_URL)

pytestmark = pytest.mark.anyio


class SnapshotImplementation(edgy.Model):
    data = edgy.fields.JSONField(default=dict)
    snapshot_for: dt = edgy.fields.DateTimeField()
    snapshot_type = edgy.fields.CharField(max_length=10)
    model_type = edgy.fields.CharField(max_length=10)

    class Meta:
        registry = models


class Snapshot(BaseTMSnapshot):
    @classmethod
    async def get_snapshot_impl(cls, *, model_type, after=None, before=None, start_snapshot=None):
        snapshots = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data = None
        current_snapshot_data = {}
        snapshot_type = SnapshotType.temporary
        query = SnapshotImplementation.query.filter(model_type=model_type).order_by("snapshot_for")
        if before is not None:
            query = query.filter(snapshot_for__lt=before)
        if after is None:
            # start_snapshot is None
            start_snapshot = await query.filter(snapshot_type="full").last()
        if start_snapshot is not None:
            query = query.filter(snapshot_for__gt=start_snapshot)
        for snap in await query:
            extracted, timepoint, snap_type = extract_snapshot_data(snap)
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
    def get_snapshot(cls, **kwargs):
        assert kwargs.pop("model_type") is None
        # model_type = cls.__name__
        return super().get_snapshot(**kwargs)


class SnapshotSubtype1(Snapshot):
    stringified: str = TMField(serializer=str)  # type: ignore
    stringified_int: int = TMField(serializer=str, deserializer=int)  # type: ignore
