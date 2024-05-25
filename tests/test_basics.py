import contextlib
from dataclasses import dataclass
from datetime import datetime as dt
from datetime import timedelta as td
from datetime import timezone

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


def test_invalid():
    events = []
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.streamline_event_times(Event1(start=dt(2024, 3, 2), stop=dt(2024, 2, 1)), events)


def test_event_within_event():
    events = [Event1(start=dt(2024, 1, 1), stop=dt(2024, 3, 1))]
    new_event = Event1(start=dt(2024, 1, 2), stop=dt(2024, 2, 1))
    occlusions = []
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.streamline_event_times(new_event, events, occlusions=occlusions)
    assert new_event.start == occlusions[0].start
    assert new_event.stop == occlusions[0].stop


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
        new_event, timeline, fallback_timezone=timezone.utc
    ) == timelineomat.TimeRangeTuple(
        start=dt(2024, 1, 3, tzinfo=timezone.utc), stop=dt(2024, 1, 4, tzinfo=timezone.utc)
    )


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
def test_ordered_insert_basic(direction):
    timeline = [
        Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)),
        # invalid event
        {},
        Event1(start=dt(2024, 1, 5), stop=dt(2024, 1, 6)),
        Event1(start=dt(2024, 1, 10), stop=dt(2024, 1, 11)),
        Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)),
    ]
    tm = timelineomat.TimelineOMat(direction=direction)
    position_offset = tm.ordered_insert(
        Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)), timeline, direction=direction
    )
    # invalid element is skipped
    if direction == "asc":
        assert position_offset == (2, 2)
        position_offset = position_offset.offset
    else:
        assert position_offset == (1, 4)
        # unset it for desc, we add asc events
        position_offset = 0
    # test stability
    position_offset = tm.ordered_insert(
        Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)), timeline, offset=position_offset
    )
    if direction == "asc":
        assert position_offset == (3, 3)
        position_offset = position_offset.offset
    else:
        assert position_offset == (1, 5)
        position_offset = 0
    # overlapping
    position_offset = tm.ordered_insert(
        Event1(start=dt(2024, 1, 7), stop=dt(2024, 1, 12)), timeline, offset=position_offset
    )
    if direction == "asc":
        assert position_offset == (5, 5)
        position_offset = position_offset.offset
    else:
        assert position_offset == (5, 2)
        position_offset = 0


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
    position, offset = tm.ordered_insert(Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)), timeline)
    assert offset == 1
    assert position == 4
    position, offset = tm.ordered_insert(Event1(start=dt(2024, 1, 12), stop=dt(2024, 1, 13)), timeline, offset=offset)
    assert offset == 2
    position, offset = tm.ordered_insert(Event1(start=dt(2024, 1, 7), stop=dt(2024, 1, 8)), timeline, offset=offset)
    assert offset == 4
    position = tm.ordered_insert(Event1(start=dt(2023, 1, 12), stop=dt(2023, 1, 13)), timeline, offset=offset).position
    assert position == 0
    # we are still descendend concerning the 2nd last insert and didn't updated the offset
    position = tm.ordered_insert(Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)), timeline, offset=offset).position
    assert position == 2


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
    position, offset = tm.streamlined_ordered_insert(Event1(start=dt(2024, 1, 7), stop=dt(2024, 1, 11)), timeline)
    assert offset == 2
    assert timeline[position].start == dt(2024, 1, 7)
    assert timeline[position].stop == dt(2024, 1, 10)
    position = tm.streamlined_ordered_insert(
        Event1(start=dt(2023, 1, 12), stop=dt(2023, 1, 13)), timeline, offset=offset
    ).position
    assert position == 0
    # we are still descendend concerning the 2nd last insert and didn't updated the offset
    position = tm.streamlined_ordered_insert(
        Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)), timeline, offset=offset
    ).position
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
