# TimelineOMat

This project allows to streamline events in timelines.
Streamlining is here to fill to adjust the event start and stop times so it fits into the gaps of the timeline and to emit an Exception if this is not possible.
The timeline should be filled with the events with higher priority first and then descend in priority.


## Installation
``` sh
pip install timelineomat
```

## Usage

There are 3 different functions which also exist as methods of the TimelineOMat class

- streamline_event_times: checks how to short the given event to fit into the timelines
- streamline_event: uses streamline_event_times plus setters to update the event and returns event
- transform_events_to_times: transforms timelines to TimeRangeTuple for e.g. databases


``` python
from dataclasses import dataclass
from datetime import datetime as dt
from timelineomat import TimelineOMat, streamline_event_times, stream_line_event, TimeRangeTuple


@dataclass
class Event:
    start: dt
    stop: dt

timeline = [Event(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
new_event = Event(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
# one time methods
# get intermediate result of new times
streamline_event_times(new_event, timeline) == TimeRangeTuple(start=dt(2024, 1, 3), stop=dt(2024, 1, 4))
# update the event
timeline.append(streamline_event(new_event, timeline))

tm = TimelineOMat()
# use method instead
tm.streamline_event_times(Event(start=dt(2024, 1, 1), stop=dt(2024, 1, )), timeline) == TimeRangeTuple(start=dt(2024, 1, 4), stop=dt(2024, 1, 5))

# now integrate in django or whatever
from django.db.models import Q

q = Q()
# this is not optimized
for timetuple in tm.transform_events_to_times(timeline):
    # timetuple is actually a 2 element tuple
    q |= Q(timepoint__range=timetuple)

```


## Tricks to integrate in different datastructures

TimelineOMat supports out of the box all kind of dicts as well as objects. It determinates
if an object is a dict and uses otherwise getattr and setattr. It even supports timelines with mixed types.

The easiest way to integrate Events in TimelineOMat with different names than start and stop is to provide
the names for `start_extractor` and `stop_extractor`.
When providing strings the string names are mirrored to the arguments:
`start_setter` and `stop_setter`. No need to set them explicitly.

### Data types of start, stop

the output format is always datetime but the input is flexible. Datetimes are nearly passed through
(naive datetimes can get a timezone set, more info later)

Int as well as float are also supported. In this case datetime.fromtimestamp is used.

In case of strings fromisodatestring is used.

#### Optional fallback timezones

All of TimelineOMat, streamline_event_times and streamline_event support an argument:
fallback_timezone

If set the timezone is used in case a naive datetime is encountered (in case of int, float, the timezone is always set).

Supported are the regular timezones of python (timezone.utc or ZoneInfo).

### TimelineOMat one-time overwrites


Given the code


``` python
from dataclasses import dataclass
from datetime import datetime as dt
from timelineomat import TimelineOMat


@dataclass
class Event:
    start: dt
    stop: dt


timeline = [Event(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
new_event1 = Event(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
new_event2 = dict(start=dt(2024, 1, 1), end=dt(2024, 1, 5))

tm = TimelineOMat()
```

it is possible to extract the data with

``` python


def one_time_overwrite_end(ev):
    if isinstance(ev, dict):
        return ev["end"]
    else:
        return ev.stop

timeline.append(tm.streamline_event(new_event1, timeline))
#

timeline.append(Event(**tm.streamline_event_times(new_event2, timeline, stop_extractor=one_time_overwrite_end)._asdict()))
```




## Tricks to improve the performance:

### Using TimelineOMat
 In case of the one time methods the extractors and setters are generated all the time when using string extractors or setters -> bad performance

Building an TimelineOMat is more efficient or alternatively provide functions for extractors and setters

### Only the last element (sorted timelines)

For handling unsorted timelines TimelineOMat iterates through all events all the time.
In case of an ordered timeline the performance can be improved by using only the last element:


``` python
from dataclasses import dataclass
from datetime import datetime as dt
from timelineomat import TimelineOMat


@dataclass
class Event:
    start: dt
    stop: dt

ordered_timeline = [Event(start=dt(2024, 1, 1), stop=dt(2024, 1, 2)), Event(start=dt(2024, 1, 2), stop=dt(2024, 1, 3))]
new_event = Event(start=dt(2024, 1, 1), stop=dt(2024, 1, 4))
# here we generate the setters and extractors only onetime
tm = TimelineOMat()
tm.streamline_event_times(new_event, ordered_timeline[-1:])
#

```


## How to integrate in db systems

DB Systems like django support range queries, which receives two element tuples. TimelineOMat can convert the timelines into such tuples (TimeRangeTuple doubles as tuple)

An example is in Usage


## How to use for sorting

simple use the streamline_event_times(...) method of TimelineOMat without any timelines as key function. By using the TimelineOMat parameter can be preinitialized

The resulting tuple can be sorted


``` python

tm = TimelineOMat()
timeline.sort(key=tm.streamline_event_times)

```

## Changes

0.3.0 rename NewTimesResult to TimeRangeTuple (the old name is still available)
