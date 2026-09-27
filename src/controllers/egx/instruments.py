from redis.asyncio import Redis

from src.actions import cached_live_json
from src.services import EGXService
from src.structs.models.responses import EGXMutualFund
from src.structs.models.responses import EGXTreasuryBond


async def get_treasury_bonds(egx: EGXService, redis: Redis) -> str:
    return await cached_live_json(
        redis,
        "treasury-bonds",
        egx.treasury_bonds,
        list[EGXTreasuryBond],
    )


async def get_mutual_funds(egx: EGXService, redis: Redis) -> str:
    return await cached_live_json(
        redis,
        "mutual-funds",
        egx.mutual_funds,
        list[EGXMutualFund],
    )
