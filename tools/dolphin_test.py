#!/usr/bin/env python3
"""Run a patched Tetris Party Deluxe disc in Dolphin with GameCube pads, and read the
game's KPAD and controller state back over Dolphin's GDB stub.

  dolphin_test.py <image> <disc id> [boot seconds]

Needs a build with the test hook (DEBUG_FEED=1 TP_PREBUILT=<dir> python3 tools/gen_prebuilt.py,
and the same TP_PREBUILT when patching the disc): the pads' responses are then written by this script
to STATE+0x40+8*port over the GDB stub.
Without the test hook the real SI path runs (pass --real): the pad is detected and idles.

Prints, for every pad button, the hold/trigger buttons the game receives.
"""
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gdbmem import Gdb

DOLPHIN = '/Applications/Dolphin.app'
PORT = 2177
STATE = 0x800043C0
KPAD0 = {'STEETR': 0x80567600, 'STEPTR': 0x80568080, 'STEJ18': 0x8057B7C0}
KPAD_STRIDE = 1400

# GameCube buttons
BTN = dict(
    A=0x01000000,
    B=0x02000000,
    X=0x04000000,
    Y=0x08000000,
    Start=0x10000000,
    Z=0x00100000,
    L=0x00400000,
    R=0x00200000,
    Up=0x00080000,
    Down=0x00040000,
    Left=0x00010000,
    Right=0x00020000,
)
NEUTRAL = (0x00808080, 0x80800000)


def prepare(user, ports=1, wiimote=False):
    shutil.rmtree(user, ignore_errors=True)
    for d in ('Config', 'GameSettings'):
        os.makedirs(os.path.join(user, d), exist_ok=True)
    dev = ''.join('SIDevice%d = %d\n' % (i, 6 if i < ports else 0) for i in range(4))
    open(os.path.join(user, 'Config', 'Dolphin.ini'), 'w').write(
        "[General]\nGDBPort = %d\n[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
        "[Core]\nMMU = True\nCPUThread = False\nCPUCore = 4\nEnableDebugging = True\nEnableCheats = False\n"
        "WiimoteContinuousScanning = False\nWiimoteControllerInterface = False\n%s"
        "[Analytics]\nPermissionAsked = True\nEnabled = False\n" % (PORT, dev))
    open(os.path.join(user, 'Config', 'WiimoteNew.ini'), 'w').write("[Wiimote1]\nSource = %d\n" % (1 if wiimote else 0))


def launch(user, image, video):
    subprocess.Popen([DOLPHIN + '/Contents/MacOS/Dolphin', '-b', '-u', user, '-e', image, '-v', video],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)


def stop(user):
    out = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if user in ln and 'Dolphin' in ln and 'dolphin_test' not in ln:
            try:
                os.kill(int(ln.split()[0]), 9)
            except ProcessLookupError:
                pass


def kpad(g, base):
    b = g.read_mem(base, 0x140)
    dev = b[0x5C]
    idx = b[0x13A]
    cnt = b[0x13B]
    # Read the newest valid sample from the ring buffer
    # When cnt > 0, the waiting samples end before idx (modulo 16)
    cl_btns, ext_type, ext_err = 0, 0, 0
    ls, rs = (0, 0), (0, 0)
    for off in range(1, 16):
        slot = (idx - off) % 16
        s_addr = base + 0x13C + slot * 56
        s_bytes = g.read_mem(s_addr, 56)
        if s_bytes[0x28] == 2: # Classic Controller sample found
            ext_type = s_bytes[0x28]
            ext_err = s_bytes[0x29]
            cl_btns = struct.unpack('>H', s_bytes[0x2A:0x2C])[0]
            ls = struct.unpack('>hh', s_bytes[0x2C:0x30])
            rs = struct.unpack('>hh', s_bytes[0x30:0x34])
            break
    return dict(dev=dev, cnt=cnt, idx=idx, ext_type=ext_type, ext_err=ext_err, cl_btns=cl_btns, ls=ls, rs=rs)



def main():
    real = '--real' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    image, rid = os.path.abspath(args[0]), args[1]
    boot = float(args[2]) if len(args) > 2 else 15
    ports = int(os.environ.get('PORTS', 1))
    user = os.path.abspath(os.environ.get('USERDIR', '/tmp/dolphin_user_tetris'))
    prepare(user, ports, wiimote=bool(os.environ.get('WIIMOTE')))
    launch(user, image, os.environ.get('VIDEO', 'Null'))
    g = None
    for _ in range(60):
        try:
            g = Gdb(port=PORT, timeout=10)
            break
        except OSError:
            time.sleep(0.5)
    if not g:
        stop(user)
        sys.exit("Could not connect to Dolphin's GDB stub on port %d" % PORT)

    g.cont()

    def feed(port, h, l):
        g.interrupt()
        g.cmd('M%x,8:%s' % (STATE + 0x40 + 8 * port, struct.pack('>II', h, l).hex()))
        g.cont()

    try:
        print('Waiting %0.1fs for game to boot...' % boot)
        time.sleep(boot)
        if not real:
            for p in range(ports):
                feed(p, *NEUTRAL)
        time.sleep(2)
        for port in range(ports):
            base = KPAD0[rid] + port * KPAD_STRIDE
            print('--- port %d (channel %d) ---' % (port + 1, port))
            g.interrupt(); k = kpad(g, base); g.cont()
            print('idle   dev=%d cnt=%d ext_type=%d cl_btns=0x%04X ls=(%d,%d)' % (
                k['dev'], k['cnt'], k['ext_type'], k['cl_btns'], *k['ls']), flush=True)
            if real:
                continue
            for name, bit in BTN.items():
                feed(port, NEUTRAL[0] | bit, NEUTRAL[1])
                time.sleep(0.4)
                g.interrupt(); k = kpad(g, base); g.cont()
                print('%-6s cl_btns=0x%04X dev=%d ext_type=%d' % (name, k['cl_btns'], k['dev'], k['ext_type']), flush=True)
                feed(port, *NEUTRAL)
                time.sleep(0.2)
            # sticks: main stick right, main stick up
            for name, h, l in (('stick R', (NEUTRAL[0] & ~0xFF00) | 0xE000, NEUTRAL[1]),
                               ('stick U', (NEUTRAL[0] & ~0xFF) | 0xE0, NEUTRAL[1])):
                feed(port, h, l)
                time.sleep(0.4)
                g.interrupt(); k = kpad(g, base); g.cont()
                print('%-6s cl_btns=0x%04X dev=%d ls=(%d,%d)' % (name, k['cl_btns'], k['dev'], *k['ls']), flush=True)
                feed(port, *NEUTRAL)
                time.sleep(0.2)
    finally:
        stop(user)


if __name__ == '__main__':
    main()
