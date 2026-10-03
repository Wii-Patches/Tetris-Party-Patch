/* GameCube controllers (ports 1-4) -> Classic Controller bridge for Tetris Party Deluxe.
 *
 * Three hooks, one blob each (see hooks.S for the register-saving entry stubs).
 * The game links the SI library but not PAD, so nothing ever polls the pads:
 * gc_poll() drives the Serial Interface's own auto-polling.
 * gc_sample() turns a pad's state into a Classic Controller sample in KPAD's ring,
 * and gc_probe() makes WPADProbe report a Classic Controller while a pad is
 * plugged into the matching port, so the game's native Classic Controller support
 * consumes it directly. Port n feeds Wii Remote channel n.
 *
 * Addresses come in as -D macros, resolved per release by anchors.py.
 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;
typedef signed char s8;

#define R32(a) (*(volatile u32 *)(a))
#define SI_OUT(n)  (0xCD006400u + 12u * (n))
#define SI_INH(n)  (0xCD006404u + 12u * (n))
#define SI_INL(n)  (0xCD006408u + 12u * (n))
#define SI_POLL    (0xCD006430u)
#define SI_COMCSR  (0xCD006434u)
#define SI_SR      (0xCD006438u)

struct st {
    u32 poll_tb;        /* last time gc_poll did its work */
    u32 busy_tb;        /* when si:: was first seen busy (0 = idle) */
    u32 probe_tb[4];    /* last SIGetType per port */
    u32 prev_btn[4];    /* the Classic Controller buttons of the previous frame's sample */
    u8 norep[4];        /* consecutive polls with NOREP latched on the port */
    u8 ours[4];         /* the last KPAD sample on this channel was ours */
};
#define ST ((volatile struct st *)STATE)

static inline u32 tb(void)
{
    u32 t;
    __asm__ volatile("mftb %0" : "=r"(t));
    return t;
}

/* a valid, error-free pad response on `chan`'s port */
static inline int gc_in(u32 chan, u32 *h, u32 *l)
{
    u32 v;

    if (chan > 3)
        return 0;
#ifdef DEBUG_FEED
    /* test builds: the pad's response is written to STATE+0x40+8*chan by a debugger */
    if (!R32(STATE + 0x40 + 8 * chan))
        return 0;
    *h = R32(STATE + 0x40 + 8 * chan);
    *l = R32(STATE + 0x44 + 8 * chan);
    return 1;
#endif
    v = R32(SI_INH(chan));
    if ((v & 0x80000000u) || !(v & 0x00800000u))
        return 0;
    *h = v;
    *l = R32(SI_INL(chan));
    return 1;
}

#if defined(HOOK_POLL)
static inline int is_pad(u32 type)
{
    return !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
}

/* one port's share of the polling; returns 1 if it started a probe */
static void poll_port(u32 n, int *probed)
{
    volatile u32 *types = (volatile u32 *)SI_TYPES;
    u32 sisr, mask, poll, sh = 8 * n;

    /* probe the port until a standard pad answers, at most every 0.25 s and one port
     * at a time: probing every frame collided with the pad's own polling on hardware */
    if (!is_pad(types[n]) && !*probed) {
        u32 now = tb();
        if (now - ST->probe_tb[n] >= 15187500u) {
            ST->probe_tb[n] = now;
            *probed = 1;
            ((u32 (*)(u32))FN_SIGETTYPE)(n);
        }
    }

    /* an unplugged pad latches NOREP; si:: never reads it (no PAD library), so
     * copy a persistent one into the type cache ourselves, which makes SIGetType
     * probe the port again once a pad is plugged back in */
    sisr = R32(SI_SR);
    if (sisr & (0x08000000u >> sh)) {
        if (ST->norep[n] < 10)
            ST->norep[n]++;
        else
            types[n] = 8;
    } else {
        ST->norep[n] = 0;
    }

    R32(SI_OUT(n)) = 0x00400300u;                          /* poll command */
    R32(SI_SR) = (sisr & (0x0F000000u >> sh)) | 0x80000000u; /* ack this port's errors, latch OUT */

    mask = is_pad(types[n]) ? (0x88u >> n) : 0;            /* ENn + VBCPYn */
    poll = R32(SI_POLL);
    if (!(poll & 0xFF00u))
        poll |= 0x0100u;
    R32(SI_POLL) = (poll & ~(0x88u >> n)) | mask;
    /* si:: rewrites SIPOLL from its own shadow on every retrace */
    R32(SI_SHADOW) = (R32(SI_SHADOW) & ~(0x88u >> n)) | mask;
}

/* Runs at the top of KPADiRead for every channel, but does its work only once per
 * frame or so, whichever channel gets there first. */
void gc_poll(u32 chan)
{
    u32 now = tb(), n;
    int probed = 0;
    s32 busy;

    if (now - ST->poll_tb < 500000u)                        /* ~8 ms */
        return;
    ST->poll_tb = now;

    for (n = 0; n < 4; n++)
        poll_port(n, &probed);

    /* a pad unplugged mid-transfer leaves si::'s global busy flag wedged
     * (nothing times it out); force it idle after a second */
    busy = (s32)R32(SI_BUSY);
    if (busy == -1) {
        ST->busy_tb = 0;
    } else if (ST->busy_tb == 0) {
        ST->busy_tb = now | 1;
    } else if (now - ST->busy_tb >= 60750000u) {
        u32 lvl = ((u32 (*)(void))FN_OSDISABLE)();
        R32(SI_BUSY) = (u32)-1;
        R32(SI_COMCSR) = 0x80000000u;
        ((void (*)(u32))FN_OSRESTORE)(lvl);
        ST->busy_tb = 0;
    }
}
#endif

#if defined(HOOK_SAMPLE)
/* Classic Controller buttons as WPAD reports them */
#define CL_UP    0x0001
#define CL_LEFT  0x0002
#define CL_ZR    0x0004
#define CL_X     0x0008
#define CL_A     0x0010
#define CL_Y     0x0020
#define CL_B     0x0040
#define CL_ZL    0x0080
#define CL_R     0x0200
#define CL_PLUS  0x0400
#define CL_HOME  0x0800
#define CL_MINUS 0x1000
#define CL_L     0x2000
#define CL_DOWN  0x4000
#define CL_RIGHT 0x8000

#define KP_RING       0x13C      /* the first 16 samples of a channel's ring, 56 bytes each */
#define KP_RING_PTR   0x4BC      /* extra sample buffer pointer */
#define KP_RING_EXTRA 0x4C0      /* extra sample buffer count */
#define SMP_SIZE      56

static inline s16 stick(u32 raw)
{
    s32 v = ((s32)(raw & 0xFF) - 128) * 3;       /* pad ~+-100 -> ~+-300 */
    if (v > 308)
        v = 308;
    if (v < -308)
        v = -308;
    return (s16)v;
}

static __attribute__((noinline)) u32 cc_buttons(u32 h, u32 l)
{
    u32 b = 0;

    /* Face buttons */
    if (h & 0x01000000u) b |= CL_A;          /* GC A -> CC A: rotate clockwise / confirm */
    if (h & 0x02000000u) b |= CL_B;          /* GC B -> CC B: rotate counter-clockwise / cancel */
    if (h & 0x04000000u) b |= CL_X;          /* GC X -> CC X: rotate clockwise */
    if (h & 0x08000000u) b |= CL_Y;          /* GC Y -> CC Y: rotate counter-clockwise */

    /* Triggers: digital click or analog threshold */
    if ((h & 0x00400000u) || ((l & 0x0000FF00u) > 0x00003200u)) b |= (CL_L | CL_ZL); /* Hold / Item */
    if ((h & 0x00200000u) || ((l & 0x000000FFu) > 0x32u))       b |= (CL_R | CL_ZR); /* Hold / Item */

    /* Menu / System buttons */
    if (h & 0x10000000u) b |= CL_PLUS;       /* GC Start -> CC +: pause */
    if (h & 0x00100000u) b |= CL_HOME;       /* GC Z -> CC HOME: HOME menu */

    /* D-pad */
    if (h & 0x00080000u) b |= CL_UP;          /* D-Up: hard drop / menu up */
    if (h & 0x00040000u) b |= CL_DOWN;        /* D-Down: soft drop / menu down */
    if (h & 0x00010000u) b |= CL_LEFT;        /* D-Left: move left / menu left */
    if (h & 0x00020000u) b |= CL_RIGHT;       /* D-Right: move right / menu right */

    /* Analog stick directions synthesized as D-pad (for stick players) */
    s32 sx = (s32)((h >> 8) & 0xFF) - 128;
    s32 sy = (s32)(h & 0xFF) - 128;
    if (sx > 48)  b |= CL_RIGHT;
    if (sx < -48) b |= CL_LEFT;
    if (sy > 48)  b |= CL_UP;
    if (sy < -48) b |= CL_DOWN;

    return b;
}

static __attribute__((noinline)) void fill_cc(u8 *s, u32 h, u32 l, u32 b)
{
    *(u16 *)(s + 0x2A) = (u16)b;
    *(s16 *)(s + 0x2C) = stick(h >> 8);      /* control stick x */
    *(s16 *)(s + 0x2E) = stick(h);           /* control stick y */
    *(s16 *)(s + 0x30) = stick(l >> 24);     /* C-stick x */
    *(s16 *)(s + 0x32) = stick(l >> 16);     /* C-stick y */
    s[0x34] = (u8)((l >> 8) & 0xFF);         /* analog L */
    s[0x35] = (u8)(l & 0xFF);                /* analog R */
    s[0x28] = 2;                             /* extension: Classic Controller */
    s[0x29] = 0;                             /* no extension error */
    s[0x36] = 0;                             /* WPAD status: OK */
}

/* ring slot `i` of channel base `k` */
static inline u8 *slot(u8 *k, u32 i)
{
    if (i < 16)
        return k + KP_RING + i * SMP_SIZE;
    return *(u8 **)(k + KP_RING_PTR) + (i - 16) * SMP_SIZE;
}

/* one fresh Classic Controller sample */
static __attribute__((noinline)) void put_sample(u8 *s, u32 h, u32 l, u32 b)
{
    u32 i;

    for (i = 0; i < SMP_SIZE; i++)
        s[i] = 0;
    fill_cc(s, h, l, b);
}

/* Called where KPADiRead asks whether samples are queued (k = the channel's KPAD struct).
 *
 * KPADRead expects at least two samples in the ring buffer to deliver input to the game.
 * We deliver two samples: the older with the previous frame's buttons (so edge triggers
 * land in the newest entry) and both with the current sticks. */
void gc_sample(u8 *k, u32 chan)
{
    u32 h, l, b, i, idx, cnt, n, i1;

    if (!gc_in(chan, &h, &l))
        return;

    b = cc_buttons(h, l);
    n = 16 + *(u32 *)(k + KP_RING_EXTRA);
    if (n > 200)
        n = 16;
    idx = k[0x13A];                  /* next slot to write; the ring wraps at n */
    cnt = k[0x13B];                  /* samples waiting */
    if (cnt == 0) {
        /* none queued: no Wii Remote (device type 0xFD), a bare one that has not
         * delivered a sample yet, or our own sample showing through */
        u8 dev = k[0x5C];
        if (!(dev == 0 || dev == 0xFD || ST->ours[chan]))
            return;
        if (idx >= n)
            idx = 0;
        i1 = idx + 1 >= n ? 0 : idx + 1;
        put_sample(slot(k, idx), h, l, ST->prev_btn[chan]);
        put_sample(slot(k, i1), h, l, b);
        k[0x13A] = i1 + 1 >= n ? 0 : i1 + 1;
        k[0x13B] = 2;
        k[0x5C] = 2;                         /* Classic Controller connected */
        ST->prev_btn[chan] = b;
        ST->ours[chan] = 1;
        return;
    }

    /* real samples queued: a bare Wii Remote gets the pad as its extension;
     * a real Nunchuk or Classic Controller is never touched */
    ST->ours[chan] = 0;
    ST->prev_btn[chan] = b;
    if (cnt > n)
        cnt = n;
    for (i = 0; i < cnt; i++) {
        u8 *s = slot(k, (idx + n - cnt + i) % n);
        if (s[0x28] == 0 || s[0x28] == 0xFD) {
            fill_cc(s, h, l, b);
            k[0x5C] = 2;
        }
    }
    if (cnt == 1) {
        /* a lone real sample: queue a copy after it so there is a second entry */
        u8 *src = slot(k, (idx + n - 1) % n);
        if (src[0x28] == 2) {
            u32 d = idx >= n ? 0 : idx;
            u8 *dst = slot(k, d);
            for (i = 0; i < SMP_SIZE; i++)
                dst[i] = src[i];
            k[0x13A] = d + 1 >= n ? 0 : d + 1;
            k[0x13B] = 2;
            k[0x5C] = 2;
        }
    }
}
#endif

#if defined(HOOK_PROBE)
/* WPADProbe(chan, &type): report a Classic Controller while a pad is plugged into the
 * port, unless the channel already has a real extension */
u32 gc_probe(u32 chan, u32 *type)
{
    u32 h, l;
    u8 *blk;
    u32 t;
    s32 status;

    if (!gc_in(chan, &h, &l))
        return 0;
    blk = *(u8 **)(WPAD_TBL + chan * 4);
    if (blk) {
        t = blk[0x8C1];
        status = *(s32 *)(blk + 0x8BC);
        if (status != -1 && (t == 1 || t == 2))
            return 0;
    }
    if (type)
        *type = 2;
    return 1;
}
#endif
