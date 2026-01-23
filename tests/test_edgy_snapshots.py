from datetime import datetime as dt

import edgy
import pytest
from edgy import Registry
from edgy.testing.client import DatabaseTestClient

from timelineomat import BaseTMSnapshot, TMField

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


class Snapshot(BaseTMSnapshot, edgy.Model):
    data = edgy.JSONField(default=dict)
    snapshot_for: dt = edgy.DateTimeField()
    snapshot_type = edgy.CharField(max_length=10)

    class Meta:
        registry = models
