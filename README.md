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

### Development Speed

I think after integrating snapshots the main focus will be on stabilization and documentation.
This is only a small library with a narrow context so I don't think there is much to improve/correct and updates will be seldom.
But proof me wrong.

## Changes

1.0.1 Fix typings.
1.0.0 Breaking Change: `ordered_insert` returns now a PositionsOffsets-Tuple instead of a tuple with just one element. Add also snapshots to the library.
      Breaking Change: Requires python >= 3.11.
0.7.0 Breaking Change: transform_events_to_times is now an iterator and returns the event as second element
0.6.0 add streamlined_ordered_insert
0.5.0 add occlusions argument
0.4.0 rename NoCallAllowed to NoCallAllowedError
0.3.0 rename NewTimesResult to TimeRangeTuple (the old name is still available)
