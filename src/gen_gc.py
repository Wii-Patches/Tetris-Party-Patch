"""Build the GameCube controller feature for one release from src/gcpad.c and src/hooks.S.

Needs devkitPPC. Three hooks (see gcpad.c); the reference (USA) main.dol is
used to find the other releases' addresses (anchors.py).
"""
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import anchors
from layout import GC_BASE, GC_END
from ops import Feature, Hook

USA_DOL = None

DEVKIT = os.environ.get('DEVKITPPC', '/opt/devkitpro/devkitPPC')
TOOL = DEVKIT + '/bin/powerpc-eabi-'
STATE = 0x800043C0          # zeroed padding in every release's first text section


def compile_hook(name, defs):
    tmp = tempfile.mkdtemp(prefix='gcpad')
    D = ['-D%s=%s' % kv for kv in defs.items()] + ['-DHOOK_' + name]
    if os.environ.get('DEBUG_FEED'):
        D.append('-DDEBUG_FEED')
    cflags = ['-O2', '-fno-unroll-loops', '-mbig-endian', '-msoft-float', '-msdata=none', '-ffreestanding', '-fno-pic',
              '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-nostdlib', '-Wall']
    subprocess.check_call([TOOL + 'gcc'] + cflags + D + ['-c', os.path.join(HERE, 'gcpad.c'), '-o', tmp + '/g.o'])
    subprocess.check_call([TOOL + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp'] + D +
                          [os.path.join(HERE, 'hooks.S'), '-o', tmp + '/h.o'])
    subprocess.check_call([TOOL + 'ld', '-T', os.path.join(HERE, 'link.ld'), '-o', tmp + '/b.elf', tmp + '/h.o', tmp + '/g.o'])
    subprocess.check_call([TOOL + 'objcopy', '-O', 'binary', tmp + '/b.elf', tmp + '/b.bin'])
    b = open(tmp + '/b.bin', 'rb').read()
    return list(struct.unpack('>%dI' % (len(b) // 4), b))


def build(region, dol):
    ref = USA_DOL if USA_DOL is not None else dol
    a = anchors.resolve(ref, dol)
    defs = {
        'STATE': '0x%08Xu' % STATE,
        'SI_TYPES': '0x%08Xu' % a['SiTypes'],
        'SI_BUSY': '0x%08Xu' % a['SiBusy'],
        'SI_SHADOW': '0x%08Xu' % a['SiShadow'],
        'FN_SIGETTYPE': '0x%08Xu' % a['SIGetType'],
        'FN_OSDISABLE': '0x%08Xu' % a['OSDisableInterrupts'],
        'FN_OSRESTORE': '0x%08Xu' % a['OSRestoreInterrupts'],
        'WPAD_TBL': '0x%08Xu' % a['WpadTbl'],
        'FN_KPAD_READ': '0x%08Xu' % a['KPADiRead'],
        'FN_KPAD_CONN': '0x%08Xu' % a['KPADiConnect'],
    }
    hooks = [('POLL', a['KPADiRead'], 0x9421FFA0, 'KPADiRead: drive the SI auto-polling for the GameCube ports'),
             ('SAMPLE', a['SampleSite'], 0x381B0001,
              'KPADiRead: turn a GameCube pad into the Classic Controller sample WPADRead stored'),
             ('PROBE', a['WPADProbe'], 0x9421FFF0, 'WPADProbe: a GameCube pad counts as a connected controller')]
    ops, cur = [], GC_BASE
    for name, site, expect, note in hooks:
        w = compile_hook(name, defs)
        assert w[-1] == 0x60000000, 'hook must end with the branch-back slot'
        w[-1] = 0
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        if orig != expect:
            raise SystemExit('%s: %s site 0x%08X holds 0x%08X, expected 0x%08X' % (region, name, site, orig, expect))
        ops.append(Hook(site, orig, w, cur, note=note))
        cur += (len(w) * 4 + 15) & ~15
    if cur > GC_END:
        raise SystemExit('gc code overflows its window: 0x%X > 0x%X' % (cur, GC_END))
    title = 'GameCube controllers'
    return Feature('gc', title, region, ops)
