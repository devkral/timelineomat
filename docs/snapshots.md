# Snapshots

Sometimes a configuration iterates over time and if you go back in time you have to restore it for a correct calculation.
Example 1: A workplan. The shifts can change and sometimes the worktimes are higher or lower, so you need the settings at the timepoint.
Example 2: A contract with adjustments.

This toolkit allows to easily build a snapshot model

## Overview

- `BaseTMSnapshot`: Abstract class to implement.
- `SnapshotType`/`SnapshotTypeVariant`: Snapshot types: full, sparse and temporary.
- `TMField`: Actual field which is used in snapshots.
- `extract_snapshot_data(obj, *, fallback_tz=None)`: Extract snapshot data from snapshot object or dict. Returns a tuple (data, timepoint, snapshot type).

### Types

- `SnapshotType.full`: A complete snapshot which overwrite everything before. Can be used to create new eras. Every snapshot timeline should start with one.
- `SnapshotType.sparse`: A sparse snapshot which overwrite snapshot data partly. Can be used for partial updates.
- `SnapshotType.temporary`: A dynamic generated snapshot type which provides a helper state. Should never be saved and only generated if you need a helper snapshot.

The type can be saved as int (stringified int is also not a problem), member name or SnapshotType enum member.
So you have plenty of choices how to save it in the storage model.
`extract_snapshot_data` will just extract the enum and validate the input.


## How to implement

1. Create a container where the snapshot data is serialized
2. Create an interface where the attributes are defined

Sometimes both can be implemented in the same class. But if you use databases you certainly want to implement it in the split model
so you can have a multiplexing snapshot implementation table.

Simple

``` python
{!> ../docs_src/snapshots/basic.py !}
```

Edgy

``` python
{!> ../docs_src/snapshots/edgy.py !}
```

## `extract_snapshot_data`

Powerful helper function for extracting snapshots. It extracts as a tuple of (data (as dict), parsed `snapshot_for`, parsed `snapshot_type`).

If the input was a dict, `extract_snapshot_data` checks first if there is a `data` item. If not it tries to unpack the dict as if it is the data item
with some additions (`snapshot_for`, `snapshot_type`).

The `snapshot_for` item or attribute is allowed to be an int (parsed as unix timestamp), a datetime object or an isoformat string. When the keyword `fallback_tz` is passed,
it uses the fallback timezone in case if no timezone could be extracted. It is recommended to use the `snapshot_fallback_tz` classvar set on the Snapshot class
because this attribute is used by the internal methods.

The `snapshot_type` item or attribute is handled lenient by `extract_snapshot_data`. It can be either a `SnapshotType` member, a member name, a stringified 
member value (integer) or directly an integer (`SnapshotType` uses integer values).
The return type is always a member of `SnapshotType`.

## `BaseTMSnapshot`

The snapshot logic object. By default setter and getters are replaced with forwards to `data`.
Fields which are handled by the snapshot (e.g. settings) are defined with `TMField`s.

It has a magic attribute named `snapshot_for`. When setting it, the data is recalculated to the valid snapshot to this timepoint. All sparse
snapshots found until then are applied.
And only explicit set fields are kept (tracked by `managed`).

If you want a different logic you can define the Subclass with `wrap_tm_accessors=False`:

``` python
class Snapshot(BaseTMSnapshot, wrap_tm_accessors=False):
    ...
```


## `TMField`

`TMField` is a specialized field for timelineomat. It takes `name` for changing the name in data.
In case `name` is empty or None, the attribute name is used.
If the used name is not in `data`, the `default_handler` is used. It takes two arguments: Snapshot instance and the used name.
By default an attribute error is thrown.
With `serializer` and `deserializer` the serializing to the data object and the deserializing from the data object can be overwritten.

## Integrate with Timeline

Imagine every snapshot being part of a timeline. Here we have only one timestamp which starts a
new era but consider every era being defined between two timestamps (start, stop) except the first and last one.

This means we have dynamic timespans (events in the other terminology). We can integrate them however by order inserting them and use
the timestamp for start and stop.

By having a timespan of zero there is no overlapping issue except two snapshots are on the same datetime for the same type. But this should be prevented.
by using e.g. unique_together in a db system.

You should use the ordering feature of the underlying infrastructure (db) instead of doing it with ordered_inserts however, because it is more performant.
