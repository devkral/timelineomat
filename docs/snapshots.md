# Snapshots

Sometimes a configuration iterates over time and if you go back in time you have to restore it for a correct calculation.
Example 1: A workplan. The shifts can change and sometimes the worktimes are higher or lower, so you need the settings at the timepoint.
Example 2: A contract with adjustments.

This toolkit allows to easily build a snapshot model which can be used to track changes in e.g. contracts or to document configuration changes.

## Overview

- `BaseTMSnapshot`: Abstract class to implement.
- `SnapshotType`/`SnapshotTypeVariant`: Snapshot types: full, sparse and temporary.
- `extract_snapshot_data(obj, *, fallback_tz=None)`: Extract snapshot data from snapshot object or dict. Returns a tuple (data, timepoint, snapshot type).

### Types

- `SnapshotType.full`: A complete snapshot which overwrite everything before. Can be used to create new eras. Every snapshot timeline should start with one.
- `SnapshotType.sparse`: A sparse snapshot which overwrite snapshot data partly. Can be used for partial updates.
- `SnapshotType.temporary`: A dynamic generated snapshot type which provides a helper state. Should never be saved and only generated if you need a helper snapshot.

The type can be saved as int (stringified int is also not a problem), member name or SnapshotType enum member.
So you have plenty of choices how to save it in the storage model.
`extract_snapshot_data` will just extract the enum and validate the input.


## How to implement

1. Create a container class where the snapshot data is serialized.
2. Create an interface where the attributes are defined.

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

The snapshot logic object. By default a setter is injected so we can log which attributes were changed.
It has following methods:

- `get_snapshots_impl`: this method must be implemented. It can either return an awaitable or the result. It can take extra keyword arguments passed to `get_snapshots`: The returned type is a Iterable of to `extract_snapshot_data` compatible objects. They are transformed to a `TMSnapshotTimeline` in `get_snaphots`.
- `get_snapshots` returns a `TMSnapshotTimeline` made from the returnal of `get_snapshots_impl`. You can pass extra keyword arguments to `get_snapshots_impl`.
  You might only want to modify this method, if you want a different `TMSnapshotTimeline`.
- `deserialize_snapshot`: To modify the loading of snapshots.
- ```
@classmethod
def process_snapshot_content_specifier(cls, content_specifier: str | None) -> str:```: This allows modifying the automatic creation of content_specifier.
  By default only the class name is used if no content_specifier was provided. But you can extend with other keys like the id of the object to which a snapshot is created.

Update related methods and properties
- `object_not_updated`: property which returns if attributes were set on the logic object which were not ignored.
- `is_attr_change_update(self, name: str, value: Any) -> bool`: When returning `False` ignore writes to attributes or their deletion and don't log them in `updated_attrs`. For non-snapshot related attributes.
- `updated_attrs` cached property, which tracks the changes. Should be accessed **after** verifying with `object_not_updated` that changes happened. Otherwise
  `object_not_updated` returns a wrong value.
  To reset use the idiom: `snapshot.__dict__.pop("updated_attrs", None)`.

### `get_snapshots`

This method returns a slice of all snapshots in form of a `TMSnapshotTimeline`. You can either
access the valid Snapshot to a specific date or iterate through the snapshots.
See (#tmsnapshottimeline)[`TMSnapshotTimeline`] for more information.

**Example**

**Tricks**
- Use `after=datetime.min` to get all snapshots.
- Don't provide any argument, to get the snapshots beginning with the last full Snapshot.

### Saving

By default `BaseTMSnapshot` makes no assumption about saving and how a save method has to look like.
In fact, it isn't even required as the changelog can be created outside of the domain Snapshot object.

However `BaseTMSnapshot` provides some methods and properties related to attribute updates, so this can be easily implemented
in the Snapshot domain object.

**Example**

```python
from pydantic import BaseModel, Field

class Snapshot(BaseTMSnapshot, BaseModel):
    data: MutableMapping[str, Any] = Field(init=False, default_factory=dict)
    snapshot_for: dt
    snapshot_type: SnapshotType

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
        return impl
```

## `TMSnapshotTimeline`

`TMSnapshotTimeline` can be accessed like a dictionary. It will return the most fitting snapshot or None.
The amount of snapshots and if any snapshot is in it can be retrieved via `len(timeline)` or `bool(timeline)`.
For efficiency it has also an `iterate` method. You can either pass a timedelta to specify a stepwidth or None to jump through the snapshots (default).
It yields (timepoint, snapshot) pairs until it is exhausted.

**Example for iterate**

``` python
from datetime import datetime, timedelta
...
# get all snapshots
all_snapshots = SnapshotModel.get_snapshots(after=datetime.min)

# 1. way, iterate through snapshots
for timepoint, snapshot in all_snapshots.iterate():
    ...
# or shorter
for timepoint, snapshot in all_snapshots:
    ...

# 2. way, iterate with step size
for timepoint, snapshot in all_snapshots.iterate(step=timedelta(day=1)):
    ...
```

You can also specify a `before` or `after` argument:

``` python
from datetime import datetime, timedelta
...
# this retrieves the snapshots with start the last full snapshot
snapshot_timeline = SnapshotModel.get_snapshots()

# 1. way, iterate through snapshots
for timepoint, snapshot in all_snapshots.iterate(after=datetime(2024, 1, 1), before=datetime(2024, 2, 1)):
    ...

# 2. way, iterate with step size
for timepoint, snapshot in all_snapshots.iterate(step=timedelta(day=1), after=datetime(2024, 1, 1), before=datetime(2024, 2, 1)):
    ...
```
This helps sifting through a timeline slice retrieved by `get_snapshots`. Note however, non-retrieved snapshots doesn't appear in the timeline.

## Integrate with Timeline (other timelineomat feature)

Imagine every snapshot being part of a timeline. Here we have only one timestamp which starts a
new era but consider every era being defined between two timestamps (start, stop) except the first and last one.

This means we have dynamic timespans (events in the other terminology). We can integrate them however by order inserting them and use
the timestamp for start and stop.

By having a timespan of zero there is no overlapping issue except two snapshots are on the same datetime for the same type. But this should be prevented.
by using e.g. unique_together in a db system.

You should use the ordering feature of the underlying infrastructure (db) instead of doing it with ordered_inserts however, because it is more performant.
