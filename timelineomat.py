__all__ = [
    "streamline_event_times",
    "streamline_event",
    "TimelineOMat",
    "SkipEvent",
]

from collections.abc import Callable
from datetime import datetime as dt
from datetime import timezone as tz
from itertools import chain
from typing import Any, NamedTuple, Optional, Union

ExtractionResult = Union[dt, float, int]
CallableExtractor = Callable[[Any], ExtractionResult]
Extractor = Union[str, CallableExtractor]
CallableSetter = Callable[[Any, dt], None]
Setter = Union[str, CallableSetter]


class SkipEvent(BaseException):
    pass


class NoCallAllowed(BaseException):
    pass


class EventResult(NamedTuple):
    start: dt
    stop: dt


def create_extractor(extractor: Extractor) -> CallableExtractor:
    if not isinstance(extractor, str):
        return extractor

    def _extractor(event: Any) -> ExtractionResult:
        try:
            if isinstance(event, dict):
                return event[extractor]
            return getattr(event, extractor)
        except (KeyError, AttributeError):
            raise SkipEvent from None

    return _extractor


def create_setter(
    setter: Setter,
    *,
    disallow_call: bool = False,
    disallow_call_instant: bool = False,
) -> CallableSetter:
    if not isinstance(setter, str):
        if disallow_call_instant:
            raise NoCallAllowed
        if disallow_call:

            def _setter(event: Any, value: dt) -> ExtractionResult:  # noqa: RET505
                raise NoCallAllowed

            return _setter
        return setter

    def _setter(event: Any, value: dt) -> None:
        if isinstance(event, dict):
            event[setter] = value
        else:
            setattr(event, setter, value)

    return _setter


def handle_result(
    result: ExtractionResult, fallback_timezone: Optional[tz] = None
) -> Optional[dt]:
    if isinstance(result, dt):
        if fallback_timezone and not result.tzinfo:
            result = result.replace(tzinfo=fallback_timezone)
        return result
    elif isinstance(result, (int, float)):  # type: ignore
        return dt.fromtimestamp(result, fallback_timezone)
    else:
        raise TypeError(f"not supported type: {type(result)}")


def streamline_event_times(
    event: Any,
    *timelines,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    filter_fn: Optional[Callable[[Any], bool]] = None,
    fallback_timezone: Optional[tz] = None,
) -> EventResult:
    start_extractor = create_extractor(start_extractor)
    stop_extractor = create_extractor(stop_extractor)
    start = handle_result(
        start_extractor(event), fallback_timezone=fallback_timezone
    )
    stop = handle_result(
        stop_extractor(event), fallback_timezone=fallback_timezone
    )
    if stop <= start:
        raise SkipEvent
    for ev in chain.from_iterable(timelines):
        if filter_fn and not filter_fn(ev):
            continue
        try:
            ev_start = handle_result(
                start_extractor(ev), fallback_timezone=fallback_timezone
            )
            ev_stop = handle_result(
                stop_extractor(ev), fallback_timezone=fallback_timezone
            )
        except SkipEvent:
            continue
        if ev_stop <= ev_start:
            continue
        if ev_start <= start and ev_stop >= stop:
            raise SkipEvent
        if ev_start <= start and ev_stop > start:
            start = ev_stop
        if ev_start < stop and ev_stop >= stop:
            stop = ev_start
        if stop <= start:
            raise SkipEvent
    return EventResult(start=start, stop=stop)


def streamline_event(
    event: Any,
    *timelines,
    start_extractor: Extractor = "start",
    stop_extractor: Extractor = "stop",
    start_setter: Optional[Setter] = None,
    stop_setter: Optional[Setter] = None,
    **kwargs,
) -> None:
    if start_setter is not None:
        start_setter = create_setter(start_setter)
    else:
        start_setter = create_setter(
            start_extractor, disallow_call_instant=True
        )
    if stop_setter is not None:
        stop_setter = create_setter(stop_setter)
    else:
        stop_setter = create_setter(stop_extractor, disallow_call_instant=True)
    result = streamline_event_times(
        event,
        chain.from_iterable(timelines),
        start_extractor=start_extractor,
        stop_extractor=stop_extractor,
        **kwargs,
    )
    start_setter(event, result.start)
    stop_setter(event, result.stop)


class TimelineOMat:
    def __init__(
        self,
        start_extractor: Extractor = "start",
        stop_extractor: Extractor = "stop",
        filter_fn: Optional[Callable[[Any], bool]] = None,
        fallback_timezone: Optional[tz] = None,
        start_setter: Optional[Setter] = None,
        stop_setter: Optional[Setter] = None,
    ):
        self.start_extractor = create_extractor(start_extractor)
        self.stop_extractor = create_extractor(stop_extractor)
        self.filter_fn = filter_fn
        self.fallback_timezone = fallback_timezone
        if start_setter is not None:
            self.start_setter = create_setter(start_setter)
        else:
            self.start_setter = create_setter(
                start_extractor, disallow_call=True
            )
        if stop_setter is not None:
            self.stop_setter = create_setter(stop_setter)
        else:
            self.stop_setter = create_setter(stop_extractor, disallow_call=True)

    def streamline_event_times(
        self,
        event: Any,
        *timelines,
    ) -> EventResult:
        return streamline_event_times(
            event,
            chain.from_iterable(timelines),
            start_extractor=self.start_extractor,
            stop_extractor=self.stop_extractor,
            filter_fn=self.filter_fn,
            fallback_timezone=self.fallback_timezone,
        )

    def streamline_event(self, event: Any, *timelines, **kwargs) -> None:
        result = self.streamline_event_times(
            event,
            chain.from_iterable(timelines),
        )
        self.start_setter(event, result.start)
        self.stop_setter(event, result.stop)
