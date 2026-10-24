"""Print every line of your portfolio, with what each listed line would receive when it sells.

Example:
    CRU_CLIENT_KEY=cru_live_... CRU_CLIENT_SECRET=... python examples/portfolio.py
"""

from cruworldwine import Cru

with Cru() as cru:
    for wine in cru.portfolio.list(limit=100).auto_paging_iter():
        print(f'{wine.wine_name} ({wine.lwin18}): {wine.total_quantity} units')
        for line in wine.portfolio:
            where = line.warehouse.current_location
            if not line.is_listed:
                print(f'  {line.portfolio_id}  {line.quantity} x {line.stock_type}, {line.stock_status}, at {where}')
                continue
            print(
                f'  {line.portfolio_id}  {line.quantity} x listed at {line.pricing.listing_price:.2f} {wine.currency}, '
                f'you receive {line.pricing.net_proceeds:.2f}, at {where}'
            )
