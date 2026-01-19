# Snapshots

Sometimes a configuration iterates over time and if you go back in time you have to restore it for a correct calculation.
Example 1: A workplan. The shifts can change and sometimes the worktimes are higher or lower, so you need the settings at the timepoint.
Example 2: A contract with adjustments.

This toolkit allows to easily build a snapshot model

## Overview

- `BaseTMSnapshot`: Abstract class to implement.
- `SnapshotType`/`SnapshotTypeVariant`: Snapshot types: full, sparse and temporary.
- `TMField`: Actual field which is used in snapshots.
- `extract_snapshot_data`: Extract snapshot data from snapshot object or dict. Returns a tuple

### Types

- `SnapshotType.full`: A complete snapshot which overwrite everything before. Can be used to create new eras. Every snapshot timeline should start with one.
- `SnapshotType.sparse`: A sparse snapshot which overwrite snapshot data partly. Can be used for updates.
- `SnapshotType.temporary`: A dynamic generated snapshot type which provides a helper state. Should never be saved only generated if you need a helper snapshot.


## How to implement

``` python

from dataclasses import dataclass, field
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

    @classmethod
    def get_snapshot_impl(cls, *, model_type, after=None, before=None, start_snapshot=None):
        snapshots = [start_snapshot] if start_snapshot is not None else []
        first_snapshot_data = None
        current_snapshot_data = {}
        snapshot_type = SnapshotType.temporary
        for snap in database_query:
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

```


## Integrate with Timeline

Imagine every snapshot being part of a timeline. Here we have only one timestamp which starts a
new era but consider every era being defined between two timestamps (start, stop) except the first and last one.

This means we have dynamic timespans (events in the other terminology). We can integrate them however by order inserting them and use
the timestamp for start and stop.

By having a timespan of zero there is no overlapping issue except two snapshots are on the same datetime for the same type. But this should be prevented.
by using e.g. unique_together in a db system.

You should use the ordering feature of the underlying infrastructure (db) instead of doing it with ordered_inserts however, because it is more performant.
