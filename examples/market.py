"""Print the bids and offers on one wine, and its last trade.

Example:
    CRU_CLIENT_KEY=cru_live_... CRU_CLIENT_SECRET=... python examples/market.py 101174520151200750
"""

import sys

from cruworldwine import Cru

if len(sys.argv) != 2:
    sys.exit('usage: market.py <lwin18>')

with Cru() as cru:
    wine = cru.market.get_wine(sys.argv[1], include_last_trade=True)
    print(f'{wine.wine_name}, prices in {wine.currency}')
    for bid in wine.bids or []:
        needs = bid.requirements
        print(
            f'  bid    {bid.price:10.2f} x {bid.quantity}  '
            f'({needs.condition_status}, delivered to {", ".join(needs.deliverable_warehouses)})'
        )
    for offer in wine.offers or []:
        print(
            f'  offer  {offer.price:10.2f} x {offer.quantity}  '
            f'({offer.condition_status}, {offer.status}, from {offer.warehouse_code})'
        )
    if wine.last_trade:
        print(f'  last traded at {wine.last_trade.price:.2f} on {wine.last_trade.traded_at}')
