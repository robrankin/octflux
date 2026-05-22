from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from octflux.core.models import ConsumptionInterval, Fuel
from octflux.core.protocols import Batch
from octflux.schema.datasets import DATASETS
from octflux.sinks.mqtt import build


class FakeMqtt:
    def __init__(self):
        self.published = []

    async def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))


def _rec(v):
    return ConsumptionInterval("159", "23J", Fuel.ELECTRICITY, False,
                               datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 5, 1, 0, 30, tzinfo=UTC), v)


@pytest.mark.integration
async def test_mqtt_publishes_one_message_per_record():
    sink = build("broker", {"base_topic": "octflux/", "qos": 1, "retain": True})
    sink._client = FakeMqtt()
    res = await sink.write(Batch(DATASETS["consumption"], [_rec(1.5), _rec(2.5)]))
    assert res.published == 2
    topic, payload, qos, retain = sink._client.published[0]
    assert topic == "octflux/consumption" and qos == 1 and retain is True
    assert json.loads(payload)["consumption"] == 1.5


@pytest.mark.integration
async def test_mqtt_empty_batch_publishes_nothing():
    sink = build("broker", {})
    sink._client = FakeMqtt()
    res = await sink.write(Batch(DATASETS["consumption"], []))
    assert res.published == 0 and sink._client.published == []
