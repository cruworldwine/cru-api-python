"""Print the best bid and offer of several wines at once, with AsyncCru.

Example:
    CRU_CLIENT_KEY=cru_live_... CRU_CLIENT_SECRET=... python examples/async_market.py 101174520151200750 ...
"""

import asyncio
import sys

from cruworldwine import AsyncCru, NotFoundError


async def best(cru: AsyncCru, lwin18: str) -> str:
    """One line for one wine: its best bid and its cheapest offer."""
    try:
        wine = await cru.market.get_wine(lwin18, depth=1)
    except NotFoundError:
        return f'{lwin18}: nothing on Cru'
    bid = f'{wine.bids[0].price:.2f}' if wine.bids else '-'
    offer = f'{wine.offers[0].price:.2f}' if wine.offers else '-'
    return f'{wine.wine_name}: bid {bid}, offer {offer} {wine.currency}'


async def main(lwins: list[str]) -> None:
    """Ask for every wine concurrently, on one connection pool."""
    async with AsyncCru() as cru:
        for line in await asyncio.gather(*(best(cru, lwin18) for lwin18 in lwins)):
            print(line)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: async_market.py <lwin18> [<lwin18> ...]')
    asyncio.run(main(sys.argv[1:]))
