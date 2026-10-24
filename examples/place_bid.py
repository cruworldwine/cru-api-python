"""Places a bid. With a partner credential it is placed at once; as a connected app it is staged,
and confirmed here only once you answer yes to its summary.

    CRU_CLIENT_KEY=cru_live_... CRU_CLIENT_SECRET=... python examples/place_bid.py 101174520151200750 6 1450
"""
import sys

from cruworldwine import APIStatusError, Cru

if len(sys.argv) != 4:
    sys.exit('usage: place_bid.py <lwin18> <quantity> <price>')
lwin18, quantity, price = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])

with Cru() as cru:
    try:
        write = cru.bids.place(lwin18=lwin18, quantity=quantity, price=price)
        if write.staged:
            answer = input(f'{write.confirmation.preview.summary} Confirm? [y/N] ')
            if answer.strip().lower() != 'y':
                sys.exit('Not placed.')
            write = cru.confirmations.confirm(write.confirmation.code)
    except APIStatusError as e:
        sys.exit(f'Refused: {e.code} {e.message} (request {e.request_id})')

    assert write.result is not None  # placed, or confirmed: no longer staged
    bid = write.result.bid
    print(f'Bid {bid.code}: {bid.quantity} x {bid.price:.2f} {bid.currency}, {bid.status}, expires {bid.expires_on}')
