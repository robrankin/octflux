"""Octoplus enrolment snapshot (GraphQL)."""

from __future__ import annotations

from ..clients.queries import OCTOPLUS
from ..core.models import OctoplusInfo
from ..core.protocols import Batch, CollectContext
from ..schema.datasets import DATASETS


class OctoplusCollector:
    name = "octoplus"
    datasets = ("octoplus",)

    async def collect(self, ctx: CollectContext) -> list[Batch]:
        acc = ctx.settings.account_number
        data = await ctx.graphql.execute(OCTOPLUS, {"accountNumber": acc})
        info = data.get("octoplusAccountInfo") or {}
        row = OctoplusInfo(
            account_number=acc, queried_at=ctx.now,
            is_enrolled=info.get("isOctoplusEnrolled"),
            enrollment_status=info.get("enrollmentStatus"),
        )
        return [Batch(DATASETS["octoplus"], [row])]


def build(options: dict) -> OctoplusCollector:
    return OctoplusCollector()
