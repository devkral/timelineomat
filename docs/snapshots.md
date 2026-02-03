# Snapshots

Sometimes a configuration iterates over time and if you go back in time you have to restore it for a correct calculation.
Example 1: A workplan. The shifts can change and sometimes the worktimes are higher or lower, so you need the settings at the timepoint.
Example 2: A contract with adjustments.

This toolkit allows to easily build a snapshot model

## Overview

- `BaseTMSnapshot`: Abstract class to implement.
- `SnapshotType`/`SnapshotTypeVariant`: Snapshot types: full, sparse and temporary.
- `TMField`: Actual field which is used in snapshots.
- `extract_snapshot_data`: Extract snapshot data from snapshot object or dict. Returns a tuple (data, timepoint, snapshot type).

### Types

- `SnapshotType.full`: A complete snapshot which overwrite everything before. Can be used to create new eras. Every snapshot timeline should start with one.
- `SnapshotType.sparse`: A sparse snapshot which overwrite snapshot data partly. Can be used for updates.
- `SnapshotType.temporary`: A dynamic generated snapshot type which provides a helper state. Should never be saved only generated if you need a helper snapshot.


## How to implement

1. Create a container where the snapshot data is serialized
2. Create an interface where the attributes are defined

Sometimes both can be implemented in the same class. But if you use databases you certainly want to implement it in the split model
so you can have


``` python
{!> ../docs_src/snapshots/basic.py !}
```



## Integrate with Timeline

Imagine every snapshot being part of a timeline. Here we have only one timestamp which starts a
new era but consider every era being defined between two timestamps (start, stop) except the first and last one.

This means we have dynamic timespans (events in the other terminology). We can integrate them however by order inserting them and use
the timestamp for start and stop.

By having a timespan of zero there is no overlapping issue except two snapshots are on the same datetime for the same type. But this should be prevented.
by using e.g. unique_together in a db system.

You should use the ordering feature of the underlying infrastructure (db) instead of doing it with ordered_inserts however, because it is more performant.
