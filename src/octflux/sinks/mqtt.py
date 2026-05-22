"""MQTT sink -- publishes each record as a JSON event to ``<base>/<dataset>``."""

from __future__ import annotations

import json

import aiomqtt
import structlog

from ..core.protocols import Batch, WriteResult

log = structlog.get_logger(__name__)


class MqttSink:
    def __init__(
        self,
        name: str,
        *,
        host: str = "localhost",
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        base_topic: str = "octflux",
        qos: int = 0,
        retain: bool = False,
    ):
        self.name = name
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._base = base_topic.rstrip("/")
        self._qos, self._retain = qos, retain
        self._client: aiomqtt.Client | None = None

    async def start(self) -> None:
        self._client = aiomqtt.Client(
            hostname=self._host, port=self._port,
            username=self._username, password=self._password,
        )
        await self._client.__aenter__()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def write(self, batch: Batch) -> WriteResult:
        topic = f"{self._base}/{batch.spec.name}"
        n = 0
        for rec in batch.records:
            payload = json.dumps(batch.spec.to_row(rec), default=str)
            await self._client.publish(topic, payload, qos=self._qos, retain=self._retain)
            n += 1
        if n:
            log.info("published", sink=self.name, table=batch.spec.name, published=n)
        return WriteResult(published=n)


def build(name: str, options: dict) -> MqttSink:
    return MqttSink(name, **options)
