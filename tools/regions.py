"""The three retail releases of Tetris Party Deluxe and their disc versions.

USA and Europe are Tetris Party Deluxe (STEETR, STEPTR); Japan is Tetris Party
Premium (STEJ18).
"""
REGIONS = {
    'STEETR': dict(label='Tetris Party Deluxe (USA)', short='USA', version=0),
    'STEPTR': dict(label='Tetris Party Deluxe (Europe)', short='Europe', version=0),
    'STEJ18': dict(label='Tetris Party Premium (Japan)', short='Japan', version=0),
}

# retail DOL sizes, to give a clear error on someone else's modified dump
DOL_SIZES = {'STEETR': 5010592, 'STEPTR': 5013280, 'STEJ18': 5093536}
