import random
from datetime import datetime as dt
from datetime import timedelta as td

import edgy
import pytest
from edgy import Registry
from edgy.testing.client import DatabaseTestClient
from edgy.testing.factory import ModelFactory
from faker import Faker

import timelineomat

database = DatabaseTestClient("sqlite:///test_db.sqlite", drop_database=True)
models = Registry(database=edgy.Database(database, force_rollback=True))

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    # this creates and drops the database
    async with database:
        await models.create_all()
        yield
        await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    # this rolls back
    async with models:
        yield


class Event(edgy.Model):
    start: dt = edgy.DateTimeField()
    stop: dt = edgy.DateTimeField()
    timeline: str = edgy.CharField(max_length=20)

    class Meta:
        registry = models


class EventFactory(ModelFactory):
    class Meta:
        model = Event


def _generate_time_tuple(faker, start):
    return start, start + td(hours=faker.random_int(1, 48))


async def _generate_event_series(name: str, amount=1000):
    faker = Faker()
    ts_start = faker.past_datetime(
        "-50d",
    )
    events = []
    for _i in range(amount):
        ts_stop = _generate_time_tuple(faker, ts_start)[1]
        events.append(Event(start=ts_start, stop=ts_stop, timeline=name))
        ts_start += td(hours=faker.random_int(1, 48))
    # prevent order
    random.shuffle(events)
    await Event.query.bulk_create(events)


async def test_multiline_ordering():
    tm = timelineomat.TimelineOMat()
    await _generate_event_series("tl1", 70)
    await _generate_event_series("tl1", 70)
    await _generate_event_series("tl2", 70)
    await _generate_event_series("tl2", 70)
    timeline1 = []
    timeline2 = await Event.query.filter(timeline="tl2").order_by("start").distinct()
    timeline_save = []
    timeline_delete = []
    for event in await Event.query.filter(timeline="tl1").order_by("start").distinct():
        occlusions = []
        try:
            tm.streamlined_ordered_insert(event, timeline1, timeline2, no_update_timelines={1}, occlusions=occlusions)
        except timelineomat.SkipEvent:
            timeline_delete.append(event.id)
            continue
        if occlusions:
            if len(occlusions) == 1:
                assert occlusions[0].stop <= event.start or occlusions[0].start >= event.stop
            else:
                assert occlusions[0].stop <= event.start and occlusions[1].start >= event.stop

            timeline_save.append(event)
    await Event.query.filter(id__in=timeline_delete).delete()
    if timeline_save:
        await Event.query.bulk_update(timeline_save, {"start", "stop"})
    # check ordering array
    last_stop = None
    for event in timeline1:
        if last_stop is not None:
            assert event.start >= last_stop
        assert event.start <= event.stop
        last_stop = event.stop

    last_stop = None
    # check ordering db
    for event in await Event.query.filter(timeline="tl1").order_by("start"):
        if last_stop is not None:
            assert event.start >= last_stop
        assert event.start <= event.stop
        last_stop = event.stop
