/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright 2026 thebcd69 (BCD)
 * BCD Material: additional terms under GPL-3.0 section 7 apply; see LICENSE-BCD.md.
 *
 * [enter] trace (diagnostic, log only; NieR:Automata's NAME ENTRY on an iPad, build 712, 2026-11-25): a session where the
 * player pressed Enter on a hardware keyboard showed no VK_RETURN at any Wine layer (no DirectInput DIK_RETURN, no
 * ImmProcessKey, no TranslateMessage), and the app's own key log stops after 60 posts, so the log could not say where the
 * key was lost. Every VK_RETURN BCD posts gets a number when it is queued (Winios.m winios_post_key_hid) and keeps it in the
 * queue event's data field, which a key event never used (always 0), so the driver's line (driver_ios.c
 * winios_drv_post_key_traced) names the same key. Plain values, no UIKit and no Wine headers: tests/host/check-enter-trace.py
 * compiles this file on its own.
 *
 * Nothing here changes a key: the event's type, code and flags are as before; only data carries the number.
 */
#ifndef WINIOS_ENTER_TRACE_H
#define WINIOS_ENTER_TRACE_H

#define WINIOS_ENTER_VK         0x0D   /* VK_RETURN: the main Enter and the keypad Enter alike */
#define WINIOS_ENTER_HID_MAIN   0x28   /* USB HID keyboard page 0x07: Keyboard Return (ENTER) */
#define WINIOS_ENTER_HID_KEYPAD 0x58   /* USB HID keyboard page 0x07: Keypad ENTER */

/* The number (24 bits, 1 and up; 0 = not traced) and the HID usage (0 = not from a hardware keyboard: the software
 * keyboard, the key bar, touch controls, key repeat) in one 32-bit word. */
static inline unsigned int winios_enter_pack(unsigned int seq, unsigned int hid)
{
    return ((seq & 0xffffffu) << 8) | (hid & 0xffu);
}

static inline unsigned int winios_enter_seq(unsigned int data) { return data >> 8; }
static inline unsigned int winios_enter_hid(unsigned int data) { return data & 0xffu; }

/* The next number: 1, 2, ... 0xffffff, then 1 again (0 means "not traced"). */
static inline unsigned int winios_enter_next(unsigned int previous)
{
    unsigned int next = (previous + 1) & 0xffffffu;
    return next ? next : 1;
}

/* Which key it was, as the log says it. */
static inline const char *winios_enter_kind(unsigned int hid)
{
    switch (hid)
    {
    case WINIOS_ENTER_HID_MAIN:   return "main";
    case WINIOS_ENTER_HID_KEYPAD: return "keypad";
    case 0:                       return "app";
    default:                      return "other";
    }
}

/* The scan code a PC keyboard sends for the key: 0x1c for the main Enter, 0xe01c (E0-prefixed) for the keypad Enter. BCD
 * posts VK_RETURN for both and the driver derives the scan code from the VK, so the logged one says what Wine received
 * and this one what a Windows game would get from the real key. */
static inline unsigned int winios_enter_pc_scan(unsigned int hid)
{
    return hid == WINIOS_ENTER_HID_KEYPAD ? 0xe01cu : 0x1cu;
}

#endif /* WINIOS_ENTER_TRACE_H */
