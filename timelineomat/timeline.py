__all__ = [
    "streamline_event_times",
    "streamline_event",
    "ordered_insert",
    "TimelineOMat",
    "SkipEvent",
    "SkipInvalidEvent",
    "SkipOccludedEvent",
    "NoCallAllowedError",
    "PositionsOffsetsTuple",
    "TimeRangeTuple",
]

from collections.abc import Callable, Iterable, Iterator, MutableSequence, Sequence
from datetime import datetime as dt
from datetime import timezone as tz
from functools import lru_cache
from itertools import chain, tee
from typing import Literal, NamedTuple, NewType, TypedDict, TypeVar, Unpack, cast


class TimeRangeTuple(NamedTuple):
    start: dt
    stop: dt


Event = TypeVar("Event")
Offset = NewType("Offset", int)
Position = NewType("Position", int)
ExtractionResult = dt | float | int | str
FilterFunction = Callable[[Event], bool]
CutHandler = Callable[[TimeRangeTuple, TimeRangeTuple, Iterator[Event]], TimeRangeTuple]
CallableExtractor = Callable[[Event], ExtractionResult]
Extractor = str | CallableExtractor
CallableSetter = Callable[[Event, dt], None]
Setter = str | CallableSetter


class PositionsOffsetsTuple(NamedTuple):
    positions: Sequence[Position]
    offsets: Sequence[Offset]


class SkipEvent(BaseException):
    pass


class SkipInvalidEvent(SkipEvent):
    pass


class SkipEmptyEvent(SkipEvent):
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


def default_cut_handler(new: TimeRangeTuple, orig: TimeRangeTuple, remaining: Iterator[Event]) -> TimeRangeTuple:
    raise SkipEvent("Noop - don't handle cut")


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


# for allowing chaining in higher code levels, expose disallow_*
def create_setter(
    setter: Setter,
    *,
    disallow_call: bool = False,
    disallow_call_instant: bool = False,
) -> CallableSetter:
    if not isinstance(setter, str):
        if disallow_call_instant:
            raise NoCallAllowedError("extractor is not a string and no setter is set")
        if disallow_call:

            def _setter(event: Event, value: dt) -> None:  # noqa: RET505
                raise NoCallAllowedError("extractor is not a string and no setter is set")

            return _setter
        return setter

    # setter is string
    def _setter_str(event: Event, value: dt) -> None:
        if isinstance(event, dict):
            event[setter] = value
        else:
            setattr(event, setter, value)

    return _setter_str


@lru_cache(1024, typed=True)
def handle_result(result: ExtractionResult, fallback_timezone: tz | None = None) -> dt:
    if isinstance(result, dt):
        if fallback_timezone and not result.tzinfo:
            result = result.replace(tzinfo=fallback_timezone)
        return result
    elif isinstance(result, int | float):
        return dt.fromtimestamp(result, fallback_timezone)
    elif isinstance(result, str):  # type: ignore
        return handle_result(dt.fromisoformat(result), fallback_timezone=fallback_timezone)
    else:
        raise TypeError(f"not supported type: {type(result)}")


def extract_tuple_from_event(
    event: Event,
    *,
    start_extractor: CallableExtractor,
    stop_extractor: CallableExtractor,
    fallback_timezone: tz | None = None,
    ensure_timespan: bool = False,
) -> TimeRangeTuple:
    start = handle_result(start_extractor(event), fallback_timezone=fallback_timezone)
    stop = handle_result(stop_extractor(event), fallback_timezone=fallback_timezone)

    if stop < start:
        raise SkipInvalidEvent("duration of the event is < 0")
    if ensure_timespan and stop == start:
        raise SkipEmptyEvent("duration of the event is = 0")

    return TimeRangeTuple(start=start, stop=stop)


def _array_window(array: Sequence[Event], offset: Offset, direction: Literal["asc", "desc"]):
    length = len(array)
    if direction == "asc":
        for pos in range(offset, length):
            yield array[pos]
    else:
        for pos in range(offset, length):
            yield array[length - pos - 1]


def _streamline_event_times(
    event: Event,
    timeline: Iterator[Event] | None,
    cut_handler: CutHandler,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    ensure_timespan: bool = False,
    filter_fn: FilterFunction | None = None,
    fallback_timezone: tz | None = None,
) -> tuple[TimeRangeTuple, TimeRangeTuple]:
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    start, stop = orig_tuple = extract_tuple_from_event(
        event,
        start_extractor=start_extractor,
        stop_extractor=stop_extractor,
        fallback_timezone=fallback_timezone,
        ensure_timespan=ensure_timespan,
    )
    if not timeline:
        return orig_tuple, orig_tuple
    is_initial_empty = start == stop
    while True:
        try:
            ev = next(timeline)
        except StopIteration:
            break
        # only check events which are not filtered
        if filter_fn and not filter_fn(ev):
            continue
        # get event time tuple
        try:
            ev_start, ev_stop = extract_tuple_from_event(
                ev,
                start_extractor=start_extractor,
                stop_extractor=stop_extractor,
                fallback_timezone=fallback_timezone,
                ensure_timespan=False,
            )
        except SkipEvent:
            continue
        # current event is within an existing event
        if ev_start <= start and ev_stop >= stop:
            raise SkipOccludedEvent(original=orig_tuple)
        # existing event is within this event, we need to cut or raise
        if start < ev_start and stop > ev_stop:
            assert start < stop
            # split iterator, if timeline is a tee object, there is already an optimization
            timeline, remaining = tee(timeline)
            start, stop = cut_handler(TimeRangeTuple(start, stop), orig_tuple, chain([ev], remaining))
        # current event is at the end of an existing event overlapping
        if ev_start <= start and ev_stop > start:
            start = ev_stop
        # current event is at the start of an existing event overlapping
        if ev_start < stop and ev_stop >= stop:
            stop = ev_start
        # check if there is still a valid timespan left after if not initial empty
        if not is_initial_empty and stop <= start:
            raise SkipOccludedEvent(original=orig_tuple)
    return TimeRangeTuple(start=start, stop=stop), orig_tuple


class _streamline_event_base_kwargs(TypedDict, total=False):
    filter_fn: FilterFunction | None
    fallback_timezone: tz | None


class _streamline_event_times_kwargs(_streamline_event_base_kwargs):
    occlusions: list[TimeRangeTuple] | None
    start_extractor: Extractor
    stop_extractor: Extractor
    ensure_timespan: bool
    cut_handler: CutHandler


def streamline_event_times(
    event: Event,
    *timelines: Iterable[Event],
    occlusions: list[TimeRangeTuple] | None = None,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    ensure_timespan: bool = False,
    cut_handler: CutHandler = default_cut_handler,
    **kwargs: Unpack[_streamline_event_base_kwargs],
) -> TimeRangeTuple:
    try:
        new_tuple, orig_tuple = _streamline_event_times(
            event,
            # None will trigger a shortcut
            chain.from_iterable(timelines) if timelines else None,
            start_extractor=start_extractor,
            stop_extractor=stop_extractor,
            ensure_timespan=ensure_timespan,
            cut_handler=cut_handler,
            **kwargs,
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


class _streamline_event_kwargs(_streamline_event_base_kwargs):
    start_extractor: Extractor
    stop_extractor: Extractor
    start_setter: Setter | None
    stop_setter: Setter | None
    occlusions: list[TimeRangeTuple] | None
    ensure_timespan: bool
    cut_handler: CutHandler


def streamline_event(
    event: Event,
    *timelines: Iterable[Event],
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    start_setter: Setter | None = None,
    stop_setter: Setter | None = None,
    occlusions: list[TimeRangeTuple] | None = None,
    ensure_timespan: bool = False,
    cut_handler: CutHandler = default_cut_handler,
    **kwargs: Unpack[_streamline_event_base_kwargs],
) -> Event:
    if not timelines:
        return event
    if start_setter is not None:
        start_setter = create_setter(start_setter)
    else:
        # because of disallow_call_instant we correctly raise for non-strings
        start_setter = create_setter(cast(str, start_extractor), disallow_call_instant=True)
    if stop_setter is not None:
        stop_setter = create_setter(stop_setter)
    else:
        # because of disallow_call_instant we correctly raise for non-strings
        stop_setter = create_setter(cast(str, stop_extractor), disallow_call_instant=True)
    new_tuple = streamline_event_times(
        event,
        *timelines,
        start_extractor=start_extractor,
        stop_extractor=stop_extractor,
        occlusions=occlusions,
        ensure_timespan=ensure_timespan,
        cut_handler=cut_handler,
        **kwargs,
    )
    start_setter(event, new_tuple.start)
    stop_setter(event, new_tuple.stop)
    return event


class _transform_events_to_times_kwargs(_streamline_event_base_kwargs):
    start_extractor: Extractor
    stop_extractor: Extractor


def transform_events_to_times(
    *timelines: Iterable[Event],
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    filter_fn: FilterFunction | None = None,
    fallback_timezone: tz | None = None,
) -> Iterable[tuple[TimeRangeTuple, Event]]:
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    if not timelines:
        return
    for ev in chain.from_iterable(timelines):
        if filter_fn and not filter_fn(ev):
            continue
        try:
            retval = (
                extract_tuple_from_event(
                    ev,
                    start_extractor=start_extractor,
                    stop_extractor=stop_extractor,
                    fallback_timezone=fallback_timezone,
                    ensure_timespan=False,
                ),
                ev,
            )
            yield retval
        except SkipEvent:
            continue


def _ordered_insert(
    event: Event,
    event_times: TimeRangeTuple,
    timeline: MutableSequence[Event],
    offset: Offset,
    direction: Literal["asc", "desc"],
    start_extractor: CallableExtractor,
    stop_extractor: CallableExtractor,
    fallback_timezone: tz | None,
    no_insert: bool,
) -> tuple[bool, Position]:
    if not len(timeline):
        if not no_insert:
            timeline.append(event)
        return no_insert, cast(Position, 0)
    last_pos = None
    length = len(timeline)
    for position in range(offset, length):
        if direction == "desc":
            position = length - position - 1
        if last_pos is None:
            last_pos = position
        ev = timeline[position]
        try:
            ev_times = extract_tuple_from_event(
                ev,
                start_extractor=start_extractor,
                stop_extractor=stop_extractor,
                fallback_timezone=fallback_timezone,
                # consider empty events
                ensure_timespan=False,
            )
        except SkipEvent:
            last_pos = position
            continue
        if direction == "asc":
            if ev_times > event_times:
                if not no_insert:
                    timeline.insert(position, event)
                return no_insert, cast(Position, position)
        else:
            if (ev_times[1], ev_times[0]) < (event_times[1], ev_times[0]):
                if not no_insert:
                    timeline.insert(cast(int, last_pos), event)
                return no_insert, cast(Position, last_pos)
        last_pos = position
    if direction == "asc":
        if not no_insert:
            timeline.append(event)
        return no_insert, cast(Position, length)
    else:
        if not no_insert:
            timeline.insert(0, event)
        return no_insert, cast(Position, 0)


class _ordered_insert_kwargs(TypedDict, total=False):
    offsets: Sequence[Offset | None | Literal[0]] | None
    no_update_timelines: set[int] | None
    start_extractor: Extractor
    stop_extractor: Extractor
    fallback_timezone: tz | None
    direction: Literal["asc", "desc"]
    ensure_timespan: bool


def ordered_insert(
    event: Event,
    *timelines: Sequence[Event],
    offsets: Sequence[Offset | None | Literal[0]] | None = None,
    no_update_timelines: set[int] | None = None,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    fallback_timezone: tz | None = None,
    direction: Literal["asc", "desc"] = "asc",
    ensure_timespan: bool = False,
) -> PositionsOffsetsTuple:
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    return_positions: list[Position] = []
    return_offsets: list[Offset] = []
    event_times = extract_tuple_from_event(
        event,
        start_extractor=start_extractor,
        stop_extractor=stop_extractor,
        fallback_timezone=fallback_timezone,
        ensure_timespan=ensure_timespan,
    )
    for count, timeline in enumerate(timelines):
        no_insert, position = _ordered_insert(
            event,
            event_times=event_times,
            timeline=cast(
                MutableSequence[Event],
                timeline,
            ),
            offset=cast(Offset, 0) if offsets is None else (offsets[count] or cast(Offset, 0)),
            direction=direction,
            fallback_timezone=fallback_timezone,
            no_insert=False if no_update_timelines is None else count in no_update_timelines,
            start_extractor=start_extractor,
            stop_extractor=stop_extractor,
        )
        return_positions.append(cast(Position, position))
        if direction == "desc":
            return_offsets.append(cast(Offset, len(timeline) - position - (0 if no_insert else 1)))
        else:
            return_offsets.append(cast(Offset, position))
    return PositionsOffsetsTuple(return_positions, return_offsets)


class _streamline_ordered_insert_kwargs(_streamline_event_kwargs):
    offsets: Sequence[Offset | None | Literal[0]] | None
    no_update_timelines: set[int] | None
    direction: Literal["asc", "desc"]
    cut_direction: Literal["asc", "desc", "occlusion"] | None


def streamlined_ordered_insert(
    event: Event,
    *timelines: Sequence[Event],
    filter_fn: FilterFunction | None = None,
    offsets: Sequence[Offset | None | Literal[0]] | None = None,
    no_update_timelines: set[int] | None = None,
    direction: Literal["asc", "desc"] = "asc",
    cut_handler: CutHandler = default_cut_handler,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    start_setter: Setter | None = None,
    stop_setter: Setter | None = None,
    fallback_timezone: tz | None = None,
    occlusions: list[TimeRangeTuple] | None = None,
    ensure_timespan: bool = False,
) -> PositionsOffsetsTuple:
    if start_setter is not None:
        start_setter = create_setter(start_setter)
    else:
        # because of disallow_call_instant we correctly raise for non-strings
        start_setter = create_setter(cast(str, start_extractor), disallow_call_instant=True)
    if stop_setter is not None:
        stop_setter = create_setter(stop_setter)
    else:
        # because of disallow_call_instant we correctly raise for non-strings
        stop_setter = create_setter(cast(str, stop_extractor), disallow_call_instant=True)
    # must be after setter extractors
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    return ordered_insert(
        streamline_event(
            event,
            *(
                _array_window(
                    timeline, cast(Offset, 0) if offsets is None else (offsets[count] or cast(Offset, 0)), direction
                )
                for count, timeline in enumerate(timelines)
            ),
            start_extractor=start_extractor,
            stop_extractor=stop_extractor,
            start_setter=start_setter,
            stop_setter=stop_setter,
            filter_fn=filter_fn,
            occlusions=occlusions,
            fallback_timezone=fallback_timezone,
            ensure_timespan=ensure_timespan,
            cut_handler=cut_handler,
        ),
        *timelines,
        no_update_timelines=no_update_timelines,
        start_extractor=start_extractor,
        stop_extractor=stop_extractor,
        offsets=offsets,
        direction=direction,
        fallback_timezone=fallback_timezone,
    )


class TimelineOMat:
    start_extractor: CallableExtractor
    stop_extractor: CallableExtractor
    start_setter: CallableSetter
    stop_setter: CallableSetter
    no_update_timelines: set[int] | None
    filter_fn: FilterFunction | None
    fallback_timezone: tz | None
    direction: Literal["asc", "desc"]
    cut_handler: CutHandler
    ensure_timespan: bool

    def __init__(
        self,
        *,
        start_extractor: Extractor = "start",
        stop_extractor: Extractor = "stop",
        start_setter: Setter | None = None,
        stop_setter: Setter | None = None,
        no_update_timelines: set[int] | None = None,
        filter_fn: FilterFunction | None = None,
        fallback_timezone: tz | None = None,
        # for ordered_insert
        direction: Literal["asc", "desc"] = "asc",
        cut_handler: CutHandler = default_cut_handler,
        ensure_timespan: bool = False,
    ):
        self.start_extractor = create_extractor(start_extractor)
        self.stop_extractor = create_extractor(stop_extractor)
        self.no_update_timelines = no_update_timelines
        self.filter_fn = filter_fn
        self.fallback_timezone = fallback_timezone
        self.direction = direction
        self.cut_handler = cut_handler
        self.ensure_timespan = ensure_timespan
        if start_setter is not None:
            self.start_setter = create_setter(start_setter)
        else:
            # because of disallow_call_instant we correctly raise for non-strings when called
            self.start_setter = create_setter(cast(str, start_extractor), disallow_call=True)
        if stop_setter is not None:
            self.stop_setter = create_setter(stop_setter)
        else:
            # because of disallow_call_instant we correctly raise for non-strings when called
            self.stop_setter = create_setter(cast(str, stop_extractor), disallow_call=True)

    def streamline_event_times(
        self, event: Event, *timelines: Iterable[Event], **kwargs: Unpack[_streamline_event_times_kwargs]
    ) -> TimeRangeTuple:
        return streamline_event_times(
            event,
            *timelines,
            occlusions=kwargs.get("occlusions"),
            cut_handler=kwargs.get("cut_handler", self.cut_handler),
            ensure_timespan=kwargs.get("ensure_timespan", self.ensure_timespan),
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            filter_fn=kwargs.get("filter_fn", self.filter_fn),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
        )

    def streamline_event(
        self, event: Event, *timelines: Iterable[Event], **kwargs: Unpack[_streamline_event_kwargs]
    ) -> Event:
        if not timelines:
            return event
        return streamline_event(
            event,
            *timelines,
            occlusions=kwargs.get("occlusions"),
            cut_handler=kwargs.get("cut_handler", self.cut_handler),
            ensure_timespan=kwargs.get("ensure_timespan", self.ensure_timespan),
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            filter_fn=kwargs.get("filter_fn", self.filter_fn),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
            start_setter=kwargs.get("start_setter", self.start_setter),
            stop_setter=kwargs.get("stop_setter", self.stop_setter),
        )

    def transform_events_to_times(
        self, *timelines: Iterable[Event], **kwargs: Unpack[_transform_events_to_times_kwargs]
    ) -> Iterable[tuple[TimeRangeTuple, Event]]:
        if not timelines:
            return []
        return transform_events_to_times(
            *timelines,
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            filter_fn=kwargs.get("filter_fn", self.filter_fn),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
        )

    def ordered_insert(
        self,
        event: Event,
        *timelines: Sequence[Event],
        **kwargs: Unpack[_ordered_insert_kwargs],
    ) -> PositionsOffsetsTuple:
        return ordered_insert(
            event,
            *timelines,
            ensure_timespan=kwargs.get("ensure_timespan", self.ensure_timespan),
            no_update_timelines=kwargs.get("no_update_timelines", self.no_update_timelines),
            offsets=kwargs.get("offsets"),
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            direction=kwargs.get("direction", self.direction),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
        )

    def streamlined_ordered_insert(
        self,
        event: Event,
        *timelines: Sequence[Event],
        **kwargs: Unpack[_streamline_ordered_insert_kwargs],
    ) -> PositionsOffsetsTuple:
        return streamlined_ordered_insert(
            event,
            *timelines,
            no_update_timelines=kwargs.get("no_update_timelines", self.no_update_timelines),
            offsets=kwargs.get("offsets"),
            occlusions=kwargs.get("occlusions"),
            cut_handler=kwargs.get("cut_handler", self.cut_handler),
            ensure_timespan=kwargs.get("ensure_timespan", self.ensure_timespan),
            start_extractor=kwargs.get("start_extractor", self.start_extractor),
            stop_extractor=kwargs.get("stop_extractor", self.stop_extractor),
            direction=kwargs.get("direction", self.direction),
            fallback_timezone=kwargs.get("fallback_timezone", self.fallback_timezone),
            filter_fn=kwargs.get("filter_fn", self.filter_fn),
            start_setter=kwargs.get("start_setter", self.start_setter),
            stop_setter=kwargs.get("stop_setter", self.stop_setter),
        )
