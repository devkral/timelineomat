import contextlib
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime as dt
from datetime import timedelta as td

import pytest
from faker import Faker

import timelineomat


@dataclass
class Event1:
    start: dt
    stop: dt


@dataclass
class Event2:
    begin: dt
    end: dt


def _generate_time_tuple(faker, start):
    return start, start + td(hours=faker.random_int(1, 48))


def _generate_event_series(_type, _variant):
    faker = Faker()
    ts_start = faker.past_datetime(
        "-200d",
    )
    events = []
    for _i in range(1000):
        ts_stop = _generate_time_tuple(faker, ts_start)[1]
        if _variant == 1:
            events.append(_type(start=ts_start, stop=ts_stop))
        else:
            events.append(_type(begin=ts_start, end=ts_stop))
        ts_start += td(hours=faker.random_int(1, 48))
    return events


def test_event1_direct():
    events = _generate_event_series(Event1, 1)
    events_finished = []
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(timelineomat.streamline_event(ev, events_finished))
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event.stop <= ev.start
        last_event = ev


def test_event2_direct():
    events = _generate_event_series(Event2, 2)
    events_finished = []
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(
                timelineomat.streamline_event(
                    ev,
                    events_finished,
                    start_extractor="begin",
                    stop_extractor="end",
                )
            )
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event.end <= ev.begin
        last_event = ev


def test_dict1_direct():
    events = _generate_event_series(dict, 1)
    events_finished = []
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(
                timelineomat.streamline_event(
                    ev,
                    events_finished,
                )
            )
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event["start"] <= ev["stop"]
        last_event = ev


def test_dict2_direct():
    events = _generate_event_series(dict, 2)
    events_finished = []
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(
                timelineomat.streamline_event(
                    ev,
                    events_finished,
                    start_extractor="begin",
                    stop_extractor="end",
                )
            )
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event["end"] <= ev["begin"]
        last_event = ev


def test_event1_timelineomat():
    events = _generate_event_series(Event1, 1)
    events_finished = []
    tm = timelineomat.TimelineOMat()
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(tm.streamline_event(ev, events_finished))
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event.stop <= ev.start
        last_event = ev


def test_event2_timelineomat():
    events = _generate_event_series(Event2, 2)
    events_finished = []
    tm = timelineomat.TimelineOMat(start_extractor="begin", stop_extractor="end")
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(tm.streamline_event(ev, events_finished))
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event.end <= ev.begin
        last_event = ev


def test_dict1_timelineomat():
    events = _generate_event_series(dict, 1)
    tm = timelineomat.TimelineOMat()
    events_finished = []
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(
                tm.streamline_event(
                    ev,
                    events_finished,
                )
            )
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event["start"] <= ev["stop"]
        last_event = ev


def test_dict2_timelineomat():
    events = _generate_event_series(dict, 2)
    tm = timelineomat.TimelineOMat(start_extractor="begin", stop_extractor="end")
    events_finished = []
    for ev in events:
        with contextlib.suppress(timelineomat.SkipEvent):
            events_finished.append(
                tm.streamline_event(
                    ev,
                    events_finished,
                )
            )
    last_event = None
    for ev in events_finished:
        if last_event:
            assert last_event["end"] <= ev["begin"]
        last_event = ev


def test_event_empty():
    events = []
    with pytest.raises(timelineomat.SkipEmptyEvent):
        timelineomat.streamline_event_times(
            Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 2)), events, ensure_timespan=True
        )
    timelineomat.streamline_event_times(
        Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 2)), events, ensure_timespan=False
    )


def test_event_empty_collision_raises():
    events = [Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 2))]
    with pytest.raises(timelineomat.SkipOccludedEvent):
        timelineomat.streamline_event_times(Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 2)), events)


def test_event_getting_empty_raises():
    events = [Event1(start=dt(2024, 2, 1), stop=dt(2024, 3, 2)), Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 3))]
    with pytest.raises(timelineomat.SkipOccludedEvent):
        timelineomat.streamline_event_times(Event1(start=dt(2024, 3, 1), stop=dt(2024, 3, 2, 1)), events)


def test_invalid():
    events = []
    with pytest.raises(timelineomat.SkipInvalidEvent):
        timelineomat.streamline_event_times(Event1(start=dt(2024, 3, 2), stop=dt(2024, 2, 1)), events)


def test_event_within_event():
    events = [Event1(start=dt(2024, 1, 1), stop=dt(2024, 3, 1))]
    new_event = Event1(start=dt(2024, 1, 2), stop=dt(2024, 2, 1))
    occlusions = []
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.streamline_event_times(new_event, events, occlusions=occlusions)
    assert new_event.start == occlusions[0].start
    assert new_event.stop == occlusions[0].stop


def test_handle_timestamps():
    events = [
        Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 2)),
        Event1(start=dt(2024, 3, 4), stop=dt(2024, 3, 4)),
        Event1(start=dt(2024, 3, 4), stop=dt(2024, 3, 8)),
    ]
    ev = Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 5))
    # fake insert
    result = timelineomat.streamlined_ordered_insert(ev, events, direction="desc", no_update_timelines={0})
    assert ev.stop == dt(2024, 3, 4)
    assert result.positions == [1]
    assert result.offsets == [2]
    assert len(events) == 3
    # let it raise (cut skip)
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.streamlined_ordered_insert(Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 5)), events)
    # insert it for real
    timelineomat.ordered_insert(ev, events)
    assert events[result.positions[0]] is ev


def test_handle_timestamp_cut_handle():
    events = [
        Event1(start=dt(2024, 3, 1), stop=dt(2024, 3, 1)),
        Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 2)),
        Event1(start=dt(2024, 3, 4), stop=dt(2024, 3, 4)),
        Event1(start=dt(2024, 3, 7), stop=dt(2024, 3, 7)),
        Event1(start=dt(2024, 3, 8), stop=dt(2024, 3, 8)),
    ]
    ev = Event1(start=dt(2024, 3, 2), stop=dt(2024, 3, 5))

    def cut_handler(new_tup, orig_tup, remaining):
        remaining = list(remaining)
        assert len(remaining) == 3
        assert remaining[0] == events[2]
        # cut on remaining[0]
        return (new_tup.start, remaining[0].start)

    tm = timelineomat.TimelineOMat(direction="desc", cut_handler=cut_handler)
    result = tm.streamlined_ordered_insert(ev, events)
    assert ev.stop == dt(2024, 3, 4)
    assert result.positions == [2]
    assert result.offsets == [3]


def test_result():
    timeline = [Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
    new_event = Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
    # one time methods
    occlusions = []
    assert timelineomat.streamline_event_times(
        new_event, timeline, occlusions=occlusions
    ) == timelineomat.TimeRangeTuple(start=dt(2024, 1, 3), stop=dt(2024, 1, 4))
    assert occlusions[0] == timelineomat.TimeRangeTuple(start=dt(2024, 1, 1), stop=dt(2024, 1, 3))
    # TimelineOMat method
    tm = timelineomat.TimelineOMat()
    occlusions = []
    assert tm.streamline_event_times(new_event, timeline, occlusions=occlusions) == timelineomat.TimeRangeTuple(
        start=dt(2024, 1, 3), stop=dt(2024, 1, 4)
    )


def test_result_fallback_utc():
    timeline = [Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
    new_event = Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
    # one time function
    assert timelineomat.streamline_event_times(
        new_event, timeline, fallback_timezone=UTC
    ) == timelineomat.TimeRangeTuple(start=dt(2024, 1, 3, tzinfo=UTC), stop=dt(2024, 1, 4, tzinfo=UTC))


def one_time_overwrite_end(ev):
    if isinstance(ev, dict):
        return ev["end"]
    else:
        return ev.stop


def test_onetime_overwrite():
    timeline = [Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
    new_event1 = Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
    new_event2 = dict(start=dt(2024, 1, 1).timestamp(), end=dt(2024, 1, 5).timestamp())

    tm = timelineomat.TimelineOMat()
    timeline.append(tm.streamline_event(new_event1, timeline))
    assert timeline[-1].stop == dt(2024, 1, 4)
    assert timeline[-1].start == dt(2024, 1, 3)
    timeline.append(
        Event1(**tm.streamline_event_times(new_event2, timeline, stop_extractor=one_time_overwrite_end)._asdict())
    )
    assert timeline[-1].stop == dt(2024, 1, 5)
    assert timeline[-1].start == dt(2024, 1, 4)
    # test conversion in TimeRangeTuple array
    assert [t for t, ev in tm.transform_events_to_times(timeline)] == [
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 3), stop=dt(2024, 1, 4)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 4), stop=dt(2024, 1, 5)),
    ]
    # test sorting

    assert [
        t for t, ev in tm.transform_events_to_times(sorted(timeline, key=tm.streamline_event_times, reverse=True))
    ] == [
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 4), stop=dt(2024, 1, 5)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 3), stop=dt(2024, 1, 4)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)),
    ]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_ordered_insert_multiline(direction):
    timeline1 = [
        Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)),
        # invalid event
        {},
        Event1(start=dt(2024, 1, 5), stop=dt(2024, 1, 6)),
        Event1(start=dt(2024, 1, 10), stop=dt(2024, 1, 11)),
        Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)),
    ]
    timeline2 = []
    timeline3_init = (Event1(start=dt(2024, 1, 11), stop=dt(2024, 1, 12)),)
    timeline3 = tuple(timeline3_init)
    tm = timelineomat.TimelineOMat(direction=direction, no_update_timelines={2})
    position_offset = tm.ordered_insert(
        Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)),
        timeline1,
        timeline2,
        timeline3,
        direction=direction,
    )
    # invalid element is skipped
    if direction == "asc":
        assert position_offset == ([2, 0, 0], [2, 0, 0])
    else:
        assert position_offset == ([1, 0, 0], [4, 0, 1])
        # unset it for desc, we add asc events
        position_offset[1][0] = 0
        position_offset[1][1] = 0
    assert timeline3 == timeline3_init
    # test stability
    position_offset = tm.ordered_insert(
        Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)),
        timeline1,
        timeline2,
        timeline3,
        offsets=position_offset.offsets,
    )
    if direction == "asc":
        assert position_offset == ([3, 1, 0], [3, 1, 0])
    else:
        assert position_offset == ([1, 0, 0], [5, 1, 1])
        position_offset[1][0] = 0
        position_offset[1][1] = 0
    assert timeline3 == timeline3_init
    # overlapping
    position_offset = tm.ordered_insert(
        Event1(start=dt(2024, 1, 7), stop=dt(2024, 1, 12)),
        timeline1,
        timeline2,
        timeline3,
        offset=position_offset,
    )
    if direction == "asc":
        assert position_offset == ([5, 2, 0], [5, 2, 0])
    else:
        # pass empty elements
        assert position_offset == ([6, 1, 0], [1, 1, 1])
        position_offset[1][0] = 0


def test_ordered_insert_desc():
    # desc is more complicated
    timeline = [
        Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)),
        # invalid event
        {},
        Event1(start=dt(2024, 1, 5), stop=dt(2024, 1, 6)),
        Event1(start=dt(2024, 1, 10), stop=dt(2024, 1, 11)),
        Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)),
    ]
    tm = timelineomat.TimelineOMat(direction="desc")
    # we need to insert descending
    positions, offsets = tm.ordered_insert(Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)), timeline)
    assert offsets == [1]
    assert positions == [4]
    positions, offsets = tm.ordered_insert(
        Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)), timeline, offsets=offsets
    )
    assert offsets == [2]
    positions, offsets = tm.ordered_insert(Event1(start=dt(2024, 1, 7), stop=dt(2024, 1, 8)), timeline, offsets=offsets)
    assert offsets == [4]
    positions = tm.ordered_insert(
        Event1(start=dt(2023, 1, 12), stop=dt(2023, 1, 13)), timeline, offsets=offsets
    ).positions
    assert positions == [0]
    # we are still descendend concerning the 2nd last insert and didn't updated the offset
    positions = tm.ordered_insert(
        Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)), timeline, offsets=offsets
    ).positions
    assert positions == [2]


def test_streamlined_ordered_insert_desc():
    # desc is more complicated
    timeline = [
        Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)),
        # invalid event
        {},
        Event1(start=dt(2024, 1, 5), stop=dt(2024, 1, 6)),
        Event1(start=dt(2024, 1, 10), stop=dt(2024, 1, 11)),
        Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)),
    ]
    tm = timelineomat.TimelineOMat(direction="desc")
    # we need to insert descending
    with pytest.raises(timelineomat.SkipEvent):
        tm.streamlined_ordered_insert(Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)), timeline)
    positions, offsets = tm.streamlined_ordered_insert(Event1(start=dt(2024, 1, 7), stop=dt(2024, 1, 11)), timeline)
    assert offsets == [2]
    assert timeline[positions[0]].start == dt(2024, 1, 7)
    assert timeline[positions[0]].stop == dt(2024, 1, 10)
    position = tm.streamlined_ordered_insert(
        Event1(start=dt(2023, 1, 12), stop=dt(2023, 1, 13)), timeline, offsets=offsets
    ).positions[0]
    assert position == 0
    # we are still descendend concerning the 2nd last insert and didn't updated the offset
    position = tm.streamlined_ordered_insert(
        Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)), timeline, offsets=offsets
    ).positions[0]
    assert position == 2


def test_invalid_rejection():
    timeline = []
    new_event1 = Event1(stop=dt(2024, 1, 1), start=dt(2024, 1, 4))
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.streamline_event_times(new_event1, timeline)
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.streamline_event_times(new_event1)
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.ordered_insert(new_event1, timeline)

    tm = timelineomat.TimelineOMat()
    with pytest.raises(timelineomat.SkipEvent):
        tm.streamline_event_times(new_event1, timeline)
    with pytest.raises(timelineomat.SkipEvent):
        tm.streamline_event_times(new_event1)
    with pytest.raises(timelineomat.SkipEvent):
        tm.ordered_insert(new_event1, timeline)
