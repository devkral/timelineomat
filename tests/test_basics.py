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


def _generate_event_series(_type, _variant):
    faker = Faker()
    ts_start = faker.past_datetime(
        "-200d",
    )
    ts_stop = faker.past_datetime(
        "-200d",
    )
    events = []
    for _i in range(1000):
        while ts_stop < ts_start:
            ts_stop += td(hours=faker.random_int(1, 48))
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
    with pytest.raises(timelineomat.SkipEvent):
        timelineomat.streamline_event_times(Event1(start=dt(2024, 1, 2), stop=dt(2024, 2, 1)), events)


def test_result():
    timeline = [Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
    new_event = Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
    # one time methods
    assert timelineomat.streamline_event_times(new_event, timeline) == timelineomat.TimeRangeTuple(
        start=dt(2024, 1, 3), stop=dt(2024, 1, 4)
    )


def test_result_fallback_utc():
    timeline = [Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event1(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
    new_event = Event1(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
    # one time methods
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
    assert tm.transform_events_to_times(timeline) == [
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 2), stop=dt(2024, 1, 3)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 3), stop=dt(2024, 1, 4)),
        timelineomat.TimeRangeTuple(start=dt(2024, 1, 4), stop=dt(2024, 1, 5)),
    ]
