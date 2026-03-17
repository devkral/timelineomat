from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime as dt
from typing import Any

from timelineomat import BaseTMSnapshot, SnapshotType, TMField, extract_snapshot_data

database_query: Any = []


@dataclass(kw_only=True)
class ExampleSnapshot(BaseTMSnapshot):
    snapshot_for: dt
    content_specifier: str
    data: dict[str, Any] = field(default_factory=dict, init=False)
    managed: set[str] = field(default_factory=set, init=False)
    snapshot_type: SnapshotType

    snapshot_field = TMField()

    def __post_init__(self, **kwargs):
        # fix data
        for k, v in self.__dict__.items():
            if isinstance(field := type(self).__dict__.get(k), TMField) and v is not field:
                self.data[k] = field.serializer(v)

    @classmethod
    def process_snapshot_content_specifier(cls, content_specifier: str | None):
        # optional, only required when content_specifiers need a processing
        return content_specifier or cls.__name__

    @classmethod
    def get_snapshots_impl(cls, *, content_specifier, after, before, start_snapshot, extra_arg=False):
        snapshots = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data = None
        snapshots = ...
        for snap in snapshots:
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
            if snap_type != SnapshotType.full and (not snapshots or first_snapshot_data is not None):
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
            snapshots.append(snap)
        if first_snapshot_data is not None:
            first_snapshot_data["snapshot_type"] = SnapshotType.temporary
            snapshots.insert(0, first_snapshot_data)
        return snapshots
