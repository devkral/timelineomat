from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime as dt
from typing import Any, Self, cast

from timelineomat import BaseTMSnapshot, SnapshotType, TMField, extract_snapshot_data
from timelineomat.snapshots import SnapshotTimelineEntry

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
    def get_snapshot_impl(  # type: ignore
        cls,
        *,
        content_specifier: str,
        after: None | dt,
        before: None | dt,
        start_snapshot: None | SnapshotTimelineEntry,
        example_extra_arg=False,
    ) -> Self | None:
        snapshots: list[SnapshotTimelineEntry] = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data: Any = None
        current_snapshot_data: dict[str, Any] = {}
        snapshot_type = SnapshotType.temporary

        for snap in database_query:
            extracted, timepoint, snap_type = extract_snapshot_data(snap, fallback_tz=cls.snapshot_fallback_tz)
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
