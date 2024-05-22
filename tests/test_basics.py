from unittest import TestCase
from dataclasses import dataclass
from datetime import datetime as dt
import timelineomat
from faker import Faker


@dataclass
class Event1:
    start: dt
    stop: dt


@dataclass
class Event2:
    begin: dt
    end: dt


class BasicTests(TestCase):
    def _generate_event_series(self, _type, _variant):
        faker = Faker()
        ts_start = faker.past_datetime(
            "-200d",
        )
        ts_stop = faker.past_datetime(
            "-200d",
        )
        events = []
        for i in range(2000):
            while ts_stop < ts_start:
                ts_stop += faker.time_delta("+2d")
            if _variant == 1:
                events.append(_type(start=ts_start, stop=ts_stop))
            else:
                events.append(_type(begin=ts_start, end=ts_stop))
            ts_start += faker.time_delta("+2d")
        return events

    def test_event1_direct(self):
        events = self._generate_event_series(Event1, 1)
        events_finished = []
        for ev in events:
            try:
                events_finished.append(
                    timelineomat.streamline_event(ev, events_finished)
                )
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event.stop, ev.start)
            last_event = ev

    def test_event2_direct(self):
        events = self._generate_event_series(Event2, 2)
        events_finished = []
        for ev in events:
            try:
                events_finished.append(
                    timelineomat.streamline_event(
                        ev,
                        events_finished,
                        start_extractor="begin",
                        stop_extractor="end",
                    )
                )
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event.end, ev.begin)
            last_event = ev

    def test_dict1_direct(self):
        events = self._generate_event_series(dict, 1)
        events_finished = []
        for ev in events:
            try:
                events_finished.append(
                    timelineomat.streamline_event(
                        ev,
                        events_finished,
                    )
                )
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event["start"], ev["stop"])
            last_event = ev

    def test_dict2_direct(self):
        events = self._generate_event_series(dict, 2)
        events_finished = []
        for ev in events:
            try:
                events_finished.append(
                    timelineomat.streamline_event(
                        ev,
                        events_finished,
                        start_extractor="begin",
                        stop_extractor="end",
                    )
                )
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event["end"], ev["begin"])
            last_event = ev

    def test_event1_timelineomat(self):
        events = self._generate_event_series(Event1, 1)
        events_finished = []
        tm = timelineomat.TimelineOMat()
        for ev in events:
            try:
                events_finished.append(tm.streamline_event(ev, events_finished))
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event.stop, ev.start)
            last_event = ev

    def test_event2_timelineomat(self):
        events = self._generate_event_series(Event2, 2)
        events_finished = []
        tm = timelineomat.TimelineOMat(
            start_extractor="begin", stop_extractor="end"
        )
        for ev in events:
            try:
                events_finished.append(tm.streamline_event(ev, events_finished))
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event.end, ev.begin)
            last_event = ev

    def test_dict1_direct(self):
        events = self._generate_event_series(dict, 1)
        tm = timelineomat.TimelineOMat()
        events_finished = []
        for ev in events:
            try:
                events_finished.append(
                    tm.streamline_event(
                        ev,
                        events_finished,
                    )
                )
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event["start"], ev["stop"])
            last_event = ev

    def test_dict2_direct(self):
        events = self._generate_event_series(dict, 2)
        tm = timelineomat.TimelineOMat(
            start_extractor="begin", stop_extractor="end"
        )
        events_finished = []
        for ev in events:
            try:
                events_finished.append(
                    tm.streamline_event(
                        ev,
                        events_finished,
                    )
                )
            except timelineomat.SkipEvent:
                print(ev)
        last_event = None
        for ev in events_finished:
            if last_event:
                self.assertLessEqual(last_event["end"], ev["begin"])
            last_event = ev
