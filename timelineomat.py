__all__ = [
    "streamline_event_times",
    "streamline_event",
    "ordered_insert",
    "TimelineOMat",
    "SkipEvent",
    "SkipInvalidEvent",
    "SkipOccludedEvent",
    "NoCallAllowedError",
    "PositionOffsetTuple",
    "TimeRangeTuple",
]

from collections.abc import Callable, Iterable, MutableSequence, Sequence
from datetime import datetime as dt
from datetime import timezone as tz
from functools import lru_cache
from itertools import chain
from typing import Literal, NamedTuple, Optional, TypeVar, Union

Event = TypeVar("Event")
Offset = TypeVar("Offset", bound=int)
Position = TypeVar("Position", bound=int)
ExtractionResult = Union[dt, float, int, str]
FilterFunction = Callable[[Event], bool]
CallableExtractor = Callable[[Event], ExtractionResult]
Extractor = Union[str, CallableExtractor]
CallableSetter = Callable[[Event, dt], None]
Setter = Union[str, CallableSetter]


class TimeRangeTuple(NamedTuple):
    start: dt
    stop: dt


class PositionOffsetTuple(NamedTuple):
    position: Position
    offset: Offset


class SkipEvent(BaseException):
    pass


class SkipInvalidEvent(SkipEvent):
    pass


class SkipOccludedEvent(SkipEvent):
    original: TimeRangeTuple

    def __init__(self, *args, original: TimeRangeTuple, **kwargs):
        super().__init__(*args, **kwargs)
        self.original = original


class NoCallAllowedError(Exception):
    pass


# old name
NewTimesResult = TimeRangeTuple
_empty = frozenset()


def create_extractor(extractor: Extractor) -> CallableExtractor:
    if not isinstance(extractor, str):
        return extractor

    def _extractor(event: Event) -> ExtractionResult:
        try:
            if isinstance(event, dict):
                return event[extractor]
            return getattr(event, extractor)
        except (KeyError, AttributeError) as exc:
            raise SkipInvalidEvent from exc

    return _extractor


def create_setter(
    setter: Setter,
    *,
    disallow_call: bool = False,
    disallow_call_instant: bool = False,
) -> CallableSetter:
    if not isinstance(setter, str):
        if disallow_call_instant:
            raise NoCallAllowedError("extractor is not a string and no explicit setter set")
        if disallow_call:

            def _setter(event: Event, value: dt) -> ExtractionResult:  # noqa: RET505
                raise NoCallAllowedError("extractor is not a string and no explicit setter set")

            return _setter
        return setter

    def _setter(event: Event, value: dt) -> None:
        if isinstance(event, dict):
            event[setter] = value
        else:
            setattr(event, setter, value)

    return _setter


@lru_cache(1024, typed=True)
def handle_result(result: ExtractionResult, fallback_timezone: Optional[tz] = None) -> dt:
    if isinstance(result, dt):
        if fallback_timezone and not result.tzinfo:
            result = result.replace(tzinfo=fallback_timezone)
        return result
    elif isinstance(result, (int, float)):
        return dt.fromtimestamp(result, fallback_timezone)
    elif isinstance(result, str):  # type: ignore
        return handle_result(dt.fromisoformat(result), fallback_timezone=fallback_timezone)
    else:
        raise TypeError(f"not supported type: {type(result)}")


def extract_tuple_from_event(
    event: Event,
    start_extractor: CallableExtractor,
    stop_extractor: CallableExtractor,
    fallback_timezone: Optional[tz] = None,
) -> TimeRangeTuple:
    start = handle_result(start_extractor(event), fallback_timezone=fallback_timezone)
    stop = handle_result(stop_extractor(event), fallback_timezone=fallback_timezone)
    if stop <= start:
        raise SkipInvalidEvent("duration <= 0")
    return TimeRangeTuple(start=start, stop=stop)


def _array_window(array: Sequence[Event], offset, direction: Literal["asc", "desc"]):
    length = len(array)
    if direction == "asc":
        for pos in range(offset, length):
            yield array[pos]
    else:
        for pos in range(offset, length):
            yield array[length - pos - 1]


def _streamline_event_times(
    event: Event,
    timeline: Iterable[Event],
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    filter_fn: Optional[FilterFunction] = None,
    fallback_timezone: Optional[tz] = None,
    **kwargs,
) -> tuple[TimeRangeTuple, TimeRangeTuple]:
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    start, stop = orig_tuple = extract_tuple_from_event(event, start_extractor, stop_extractor, fallback_timezone)
    if not timeline:
        return orig_tuple, orig_tuple
    for ev in timeline:
        if filter_fn and not filter_fn(ev):
            continue
        try:
            ev_start, ev_stop = extract_tuple_from_event(ev, start_extractor, stop_extractor, fallback_timezone)
        except SkipEvent:
            continue
        if ev_start <= start and ev_stop >= stop:
            raise SkipOccludedEvent(original=orig_tuple)
        if ev_start <= start and ev_stop > start:
            start = ev_stop
        if ev_start < stop and ev_stop >= stop:
            stop = ev_start
        if stop <= start:
            raise SkipOccludedEvent(original=orig_tuple)
    return TimeRangeTuple(start=start, stop=stop), orig_tuple


def streamline_event_times(
    event: Event,
    *timelines,
    occlusions: Optional[list[TimeRangeTuple]] = None,
    **kwargs,
) -> TimeRangeTuple:
    try:
        new_tuple, orig_tuple = _streamline_event_times(
            event, chain.from_iterable(timelines) if timelines else _empty, **kwargs
        )
    except SkipOccludedEvent as exc:
        if occlusions is not None:
            occlusions.append(exc.original)
        raise exc
    if new_tuple != orig_tuple and occlusions is not None:
        if orig_tuple.start != new_tuple.start:
            occlusions.append(TimeRangeTuple(start=orig_tuple.start, stop=new_tuple.start))
        if orig_tuple.stop != new_tuple.stop:
            occlusions.append(TimeRangeTuple(start=new_tuple.stop, stop=orig_tuple.stop))
    return new_tuple


def streamline_event(
    event: Event,
    *timelines,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    start_setter: Optional[Setter] = None,
    stop_setter: Optional[Setter] = None,
    **kwargs,
) -> Event:
    if not timelines:
        return event
    if start_setter is not None:
        start_setter = create_setter(start_setter)
    else:
        start_setter = create_setter(start_extractor, disallow_call_instant=True)
    if stop_setter is not None:
        stop_setter = create_setter(stop_setter)
    else:
        stop_setter = create_setter(stop_extractor, disallow_call_instant=True)
    new_tuple = streamline_event_times(
        event,
        chain.from_iterable(timelines),
        start_extractor=start_extractor,
        stop_extractor=stop_extractor,
        **kwargs,
    )
    start_setter(event, new_tuple.start)
    stop_setter(event, new_tuple.stop)
    return event


def transform_events_to_times(
    *timelines,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    filter_fn: Optional[FilterFunction] = None,
    fallback_timezone: Optional[tz] = None,
    **kwargs,
) -> Iterable[tuple[TimeRangeTuple, Event]]:
    assert "occlusions" not in kwargs, "occlusions not supported for this function"
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    if not timelines:
        return
    for ev in chain.from_iterable(timelines):
        if filter_fn and not filter_fn(ev):
            continue
        try:
            retval = (extract_tuple_from_event(ev, start_extractor, stop_extractor, fallback_timezone), ev)
            yield retval
        except SkipEvent:
            continue


def _ordered_insert(
    event: Event,
    timeline: MutableSequence[Event],
    *,
    offset: Offset = 0,
    direction: Literal["asc", "desc"] = "asc",
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    fallback_timezone: Optional[tz] = None,
    **kwargs,
) -> Position:
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    event_times = extract_tuple_from_event(event, start_extractor, stop_extractor, fallback_timezone)

    if not len(timeline):
        timeline.append(event)
        return 0
    last_pos = None
    length = len(timeline)
    for position in range(offset, length):
        if direction == "desc":
            position = length - position - 1
        ev = timeline[position]
        try:
            ev_times = extract_tuple_from_event(ev, start_extractor, stop_extractor, fallback_timezone)
        except SkipEvent:
            last_pos = position
            continue
        if direction == "asc":
            if ev_times > event_times:
                timeline.insert(position, event)
                return position
        else:
            if ev_times < event_times:
                timeline.insert(last_pos, event)
                return last_pos
        last_pos = position
    if direction == "asc":
        timeline.append(event)
        return length
    else:
        timeline.insert(0, event)
        return 0


def ordered_insert(
    event: Event,
    timeline: MutableSequence[Event],
    *,
    direction: Literal["asc", "desc"] = "asc",
    **kwargs,
) -> PositionOffsetTuple:
    assert "occlusions" not in kwargs, "occlusions not supported for this function"
    position = _ordered_insert(event, timeline, direction=direction, **kwargs)
    if direction == "desc":
        return PositionOffsetTuple(position=position, offset=len(timeline) - position - 1)
    return PositionOffsetTuple(position=position, offset=position)


def streamlined_ordered_insert(
    event: Event,
    timeline: MutableSequence[Event],
    *,
    filter_fn: Optional[FilterFunction] = None,
    occlusions: Optional[list[TimeRangeTuple]] = None,
    direction: Literal["asc", "desc"] = "asc",
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    start_setter: Optional[Setter] = None,
    stop_setter: Optional[Setter] = None,
    offset: int = 0,
    **kwargs,
) -> PositionOffsetTuple:
    if start_setter is not None:
        start_setter = create_setter(start_setter)
    else:
        start_setter = create_setter(start_extractor, disallow_call_instant=True)
    if stop_setter is not None:
        stop_setter = create_setter(stop_setter)
    else:
        stop_setter = create_setter(stop_extractor, disallow_call_instant=True)
    # must be after setter extractors
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    return ordered_insert(
        streamline_event(
            event,
            _array_window(timeline, offset, direction),
            occlusions=occlusions,
            start_extractor=start_extractor,
            stop_extractor=stop_extractor,
            start_setter=start_setter,
            stop_setter=stop_setter,
            **kwargs,
        ),
        timeline,
        start_extractor=start_extractor,
        stop_extractor=stop_extractor,
        offset=offset,
        direction=direction,
        **kwargs,
    )


class TimelineOMat:
    start_extractor: CallableExtractor
    stop_extractor: CallableExtractor
    start_setter: CallableSetter
    stop_setter: CallableSetter
    filter_fn: Optional[FilterFunction]
    fallback_timezone: Optional[tz]

    def __init__(
        self,
        *,
        start_extractor: Extractor = "start",
        stop_extractor: Extractor = "stop",
        start_setter: Optional[Setter] = None,
        stop_setter: Optional[Setter] = None,
        filter_fn: Optional[FilterFunction] = None,
        fallback_timezone: Optional[tz] = None,
        # for ordered_insert
        direction: Literal["asc", "desc"] = "asc",
    ):
        self.start_extractor = create_extractor(start_extractor)
        self.stop_extractor = create_extractor(stop_extractor)
        self.filter_fn = filter_fn
        self.fallback_timezone = fallback_timezone
        self.direction = direction
        if start_setter is not None:
            self.start_setter = create_setter(start_setter)
        else:
            self.start_setter = create_setter(start_extractor, disallow_call=True)
        if stop_setter is not None:
            self.stop_setter = create_setter(stop_setter)
        else:
            self.stop_setter = create_setter(stop_extractor, disallow_call=True)

    def streamline_event_times(self, event: Event, *timelines, **kwargs) -> TimeRangeTuple:
        if timelines:
            return streamline_event_times(
                event,
                chain.from_iterable(timelines),
                start_extractor=kwargs.get("start_extractor", self.start_extractor),
                stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
                filter_fn=kwargs.get("filter_fn", self.filter_fn),
                fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
                occlusions=kwargs.get("occlusions", None),
            )
        else:
            return streamline_event_times(
                event,
                start_extractor=kwargs.get("start_extractor", self.start_extractor),
                stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
                filter_fn=kwargs.get("filter_fn", self.filter_fn),
                fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
                occlusions=kwargs.get("occlusions", None),
            )

    def streamline_event(self, event: Event, *timelines, **kwargs) -> Event:
        if not timelines:
            return event
        return streamline_event(
            event,
            chain.from_iterable(timelines),
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            filter_fn=kwargs.get("filter_fn", self.filter_fn),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
            start_setter=kwargs.get("start_setter", self.start_setter),
            stop_setter=kwargs.get("stop_setter", self.stop_setter),
            occlusions=kwargs.get("occlusions", None),
        )

    def transform_events_to_times(self, *timelines, **kwargs) -> Iterable[tuple[TimeRangeTuple, Event]]:
        assert "occlusions" not in kwargs, "occlusions not supported for this function"
        if not timelines:
            return []
        return transform_events_to_times(
            chain.from_iterable(timelines),
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            filter_fn=kwargs.get("filter_fn", self.filter_fn),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
        )

    def ordered_insert(
        self,
        event: Event,
        timeline: MutableSequence[Event],
        *,
        offset: Offset = 0,
        **kwargs,
    ) -> PositionOffsetTuple:
        assert "occlusions" not in kwargs, "occlusions not supported for this function"
        return ordered_insert(
            event,
            timeline,
            offset=offset,
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            direction=kwargs.get("direction", self.direction),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
        )

    def streamlined_ordered_insert(
        self,
        event: Event,
        timeline: MutableSequence[Event],
        *,
        offset: Offset = 0,
        **kwargs,
    ) -> PositionOffsetTuple:
        return streamlined_ordered_insert(
            event,
            timeline,
            offset=offset,
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            direction=kwargs.get("direction", self.direction),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
            filter_fn=kwargs.get("filter_fn", self.filter_fn),
            start_setter=kwargs.get("start_setter", self.start_setter),
            stop_setter=kwargs.get("stop_setter", self.stop_setter),
            occlusions=kwargs.get("occlusions", None),
        )
