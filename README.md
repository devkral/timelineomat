# TimelineOMat

TimelineOMat offers two functions:

1. Streamline events into timelines and raise in case of occlusions
2. Having a snapshot timeline.


## Installation
``` sh
pip install timelineomat
```

## Usage

(./docs/timeline.md)[Timeline]

(./docs/snapshots.md)[Snapshots]

## Development

For more speed and efficiency this projects uses uv instead of pip.
This means you have to install the uv package manager additionally for development.

See how to install here:

https://pypi.org/project/uv/

## Changes

0.8.0 Add snapshots
0.7.0 Breaking Change: transform_events_to_times is now an iterator and returns the event as second element
0.6.0 add streamlined_ordered_insert
0.5.0 add occlusions argument
0.4.0 rename NoCallAllowed to NoCallAllowedError
0.3.0 rename NewTimesResult to TimeRangeTuple (the old name is still available)
