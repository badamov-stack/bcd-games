#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright 2026 thebcd69 (BCD)
# BCD Material: additional terms under GPL-3.0 section 7 apply; see LICENSE-BCD.md.
"""The [enter] trace (diagnostic, log only; NieR:Automata's NAME ENTRY, build 712, 2026-11-25).

A hardware Enter press reached no Wine layer, and the app's key log stops after 60 posts. Every Enter and keypad Enter is
now logged where GCKeyboard delivers it (HardwareInput.key, before the focus gate), with what became of it, where UIKit
types a newline (the two text bridges), where Winios.m queues it (numbered) and where the driver sends it (the same number,
the scan code, the status, the foreground window and its focus). This checks, with no Wine and no device:
  C (Winios.m's queue and drain, compiled with stubs; driver_ios.c's line; winios_enter_trace.h):
    - the number and the HID usage survive the queue; every other key still carries data 0;
    - each key reaches the driver with the code and flags it had before, in order, and nothing waits;
    - every VK_RETURN is logged, far beyond the old 60-line cap; a full queue says DROPPED;
    - the driver's line names the key, its scan code and who receives it, and says when nobody does;
  Swift (the pure EnterTrace, when a Swift compiler is at hand; macOS CI runs it with --require-swift):
    - kinds, PC scan codes, verdicts, and the text bridges' newline line;
  source:
    - the trace sits before the focus gate, posts nothing of its own and adds no delay; the key paths are as before.
Needs python3 and a C compiler.
"""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--require-swift', action='store_true')
args = parser.parse_args()

root = Path(__file__).resolve().parents[2]
app = root / 'app/Madeira'
winios = (app / 'Winios/Winios.m').read_text()
driver = (root / 'build/win32u-unix/driver_ios.c').read_text()
hardware = (app / 'HardwareInput.swift').read_text()
content = (app / 'ContentView.swift').read_text()
library = (app / 'Library.swift').read_text()


def between(source, start, end):
    i = source.index(start)
    return source[i:source.index(end, i)]


def function(source, signature):
    """A C function or a top-level Swift declaration: up to the first closing brace in column 0."""
    start = source.index(signature)
    return source[start:source.index('\n}\n', start) + 3]


def method(source, signature):
    """A Swift method indented by four spaces: up to its closing brace at that indent."""
    start = source.index(signature)
    return source[start:source.index('\n    }\n', start) + 7]


failures = 0


def check(name, ok, detail=''):
    global failures
    print(('ok   ' if ok else 'FAIL ') + name + ('' if ok else f'\n     {detail}'))
    if not ok:
        failures += 1


# ---- C: the queue, the drain and the driver's line -------------------------------------------------------------------
queue = between(winios, '#define WINIOS_RING_SIZE', 'static void winios_game_cursor_touch(int x, int y);')
posting = between(winios, 'static int winios_vk_types_text(int vk) {', '/* The input queue, drained on a Wine thread')
drain = between(winios, 'static BOOL winios_drain_input(void) {', 'BOOL winios_pProcessEvents(DWORD mask) {')
line_fn = between(driver, 'static int winios_enter_trace_line(', '/* end winios_enter_trace_line */')

c = r'''
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "winios_enter_trace.h"
typedef int BOOL;
typedef unsigned int UINT;
typedef unsigned int DWORD;
typedef void *HWND;
#define TRUE 1
#define FALSE 0
#define MOUSEEVENTF_ABSOLUTE 0x8000
#define KEYEVENTF_EXTENDEDKEY 0x0001
static double CACurrentMediaTime(void) { return 0; }
static void winios_drv_post_text(unsigned int scalar, unsigned short vk, int shift) {}
static void winios_drv_post_mouse(int x, int y, unsigned int flags, unsigned int data, void *hwnd) {}
static struct { unsigned short vk; unsigned int flags, seq, hid; } got[4096];
static int ngot;
static void winios_drv_post_key_traced(unsigned short vk, unsigned int flags, unsigned int seq, unsigned int hid) {
    assert(ngot < 4096); got[ngot].vk = vk; got[ngot].flags = flags; got[ngot].seq = seq; got[ngot].hid = hid; ngot++;
}
''' + queue + posting + drain + line_fn + r'''
static int count_lines(const char *path, const char *needle) {
    char buf[1024]; int n = 0; FILE *f = fopen(path, "r");
    assert(f);
    while (fgets(buf, sizeof buf, f)) if (strstr(buf, needle)) n++;
    fclose(f);
    return n;
}
static int contains(const char *path, const char *needle) { return count_lines(path, needle) > 0; }
static void drain_all(void) { while (g_input_q.tail != g_input_q.head) winios_drain_input(); }
int main(int argc, char **argv) {
    /* winios_enter_trace.h */
    assert(winios_enter_seq(winios_enter_pack(1, 0x28)) == 1 && winios_enter_hid(winios_enter_pack(1, 0x28)) == 0x28);
    assert(winios_enter_seq(winios_enter_pack(0xffffff, 0x58)) == 0xffffff && winios_enter_hid(winios_enter_pack(0xffffff, 0x58)) == 0x58);
    assert(winios_enter_pack(5, 0) != 0 && winios_enter_pack(0, 0) == 0);
    assert(winios_enter_next(0) == 1 && winios_enter_next(41) == 42 && winios_enter_next(0xffffff) == 1);
    assert(!strcmp(winios_enter_kind(0x28), "main") && !strcmp(winios_enter_kind(0x58), "keypad"));
    assert(!strcmp(winios_enter_kind(0), "app") && !strcmp(winios_enter_kind(0x04), "other"));
    assert(winios_enter_pc_scan(0x28) == 0x1c && winios_enter_pc_scan(0x58) == 0xe01c && winios_enter_pc_scan(0) == 0x1c);
    puts("PASS: numbering, HID usage, kinds and PC scan codes (winios_enter_trace.h)");

    /* every key keeps its code and flags; only VK_RETURN gets a number */
    freopen(argv[1], "w", stderr);
    winios_post_key('A', 1); winios_post_key('A', 0);
    winios_post_key_hid(0x0D, 1, 0x28); winios_post_key_hid(0x0D, 0, 0x28);
    winios_post_key_hid(0x0D, 1, 0x58); winios_post_key_hid(0x0D, 0, 0x58);
    winios_post_key(0x0D, 1); winios_post_key(0x0D, 0);      /* the software keyboard, the key bar, touch controls */
    winios_post_key(0x1B, 1); winios_post_key(0x1B, 0);
    drain_all();
    assert(ngot == 10);
    static const unsigned short vks[10] = {'A','A',0x0D,0x0D,0x0D,0x0D,0x0D,0x0D,0x1B,0x1B};
    for (int i = 0; i < 10; i++) {
        assert(got[i].vk == vks[i]);
        assert(got[i].flags == ((i & 1) ? KEYEVENTF_KEYUP : 0));   /* down, up: as before */
    }
    assert(got[0].seq == 0 && got[0].hid == 0 && got[1].seq == 0 && got[8].seq == 0 && got[9].seq == 0);
    assert(got[2].seq == 1 && got[2].hid == 0x28 && got[3].seq == 2 && got[3].hid == 0x28);
    assert(got[4].seq == 3 && got[4].hid == 0x58 && got[5].seq == 4 && got[5].hid == 0x58);
    assert(got[6].seq == 5 && got[6].hid == 0 && got[7].seq == 6 && got[7].hid == 0);
    puts("PASS: each key reaches the driver with its old code and flags, in order; VK_RETURN numbered with its HID usage");

    /* far beyond the old 60-line cap: every Enter is logged */
    ngot = 0;
    for (int i = 0; i < 200; i++) { winios_post_key_hid(0x0D, 1, 0x28); winios_post_key_hid(0x0D, 0, 0x28); drain_all(); }
    assert(ngot == 400);
    fflush(stderr);
    assert(count_lines(argv[1], "[enter] #") == 406);
    assert(contains(argv[1], "[enter] #1 queued down hid=0x28 kind=main queue=2/255\n"));
    assert(contains(argv[1], "[enter] #4 queued up hid=0x58 kind=keypad"));
    assert(contains(argv[1], "[enter] #5 queued down hid=0x00 kind=app"));
    assert(contains(argv[1], "[enter] #406 queued up hid=0x28 kind=main"));
    assert(!contains(argv[1], "DROPPED"));
    puts("PASS: every VK_RETURN is logged when queued (406 of 406, past the old 60-line cap)");

    /* a full queue keeps the newest event out: the trace says so */
    ngot = 0;
    for (int i = 0; i < 255; i++) winios_post_key('B', i & 1);
    winios_post_key_hid(0x0D, 1, 0x28);
    fflush(stderr);
    assert(contains(argv[1], "[enter] #407 queued down hid=0x28 kind=main queue=255/255 -> DROPPED (queue full)"));
    drain_all();
    assert(ngot == 255 && got[254].vk == 'B');   /* the Enter never reached the driver */
    puts("PASS: an Enter the full queue kept out is logged as DROPPED");

    /* the driver's line */
    char buf[512];
    winios_enter_trace_line(buf, sizeof buf, 7, 0x28, 0, 0x1c, 0, (HWND)0x1005e, 0xac, (HWND)0x1005e, (HWND)0x1005e);
    assert(strstr(buf, "[enter] #7 drv down hid=0x28 kind=main vk=0xd scan=0x1c ext=0 (a PC keyboard's Enter sends 0x1c) status=0x0 "));
    assert(strstr(buf, "fg-tid=00ac") && strstr(buf, "focus=0x1005e") && !strstr(buf, "NO FOREGROUND"));
    winios_enter_trace_line(buf, sizeof buf, 8, 0x58, KEYEVENTF_KEYUP, 0x1c, 0, (HWND)0x1005e, 0xac, NULL, (HWND)0x1005e);
    assert(strstr(buf, "#8 drv up hid=0x58 kind=keypad") && strstr(buf, "(a PC keyboard's keypad Enter sends 0xe01c)"));
    assert(strstr(buf, "(the foreground thread has no focus window)"));
    winios_enter_trace_line(buf, sizeof buf, 0, 0, 0, 0x1c, 0, NULL, 0, NULL, NULL);
    assert(strstr(buf, "[enter] #0 drv down hid=0x00 kind=app") && strstr(buf, "NO FOREGROUND WINDOW: the key reaches no thread"));
    puts("PASS: the driver's line: number, key, scan code, status, foreground thread and its focus; no foreground said plainly");
    return 0;
}
'''

cc = os.environ.get('CC', 'cc')
with tempfile.TemporaryDirectory(prefix='bcd-enter-trace-') as temp:
    temp = Path(temp)
    (temp / 'test.c').write_text(c)
    r = subprocess.run([cc, '-std=gnu11', '-pthread', '-Wall', '-Wno-unused-function', '-I', str(app / 'Winios'),
                        str(temp / 'test.c'), '-o', str(temp / 'c-test')], capture_output=True, text=True)
    check('the queue, the drain and the driver line compile with stubs', r.returncode == 0, r.stderr[-3000:])
    if r.returncode == 0:
        r = subprocess.run([str(temp / 'c-test'), str(temp / 'stderr.log')], capture_output=True, text=True)
        print(r.stdout, end='')
        log = (temp / 'stderr.log').read_text() if (temp / 'stderr.log').exists() else ''
        check('the C checks pass', r.returncode == 0, ((r.stderr or '') + log)[-2000:])

# ---- Swift: EnterTrace (pure section of HardwareInput.swift) ------------------------------------------------------
enter_trace = function(hardware, 'enum EnterTrace {')
swift = enter_trace + r'''
assert(EnterTrace.isEnter(hid: 0x28) && EnterTrace.isEnter(hid: 0x58) && !EnterTrace.isEnter(hid: 0x51))
assert(EnterTrace.kind(hid: 0x28) == "main" && EnterTrace.kind(hid: 0x58) == "keypad" && EnterTrace.kind(hid: 0) == "app")
assert(EnterTrace.pcScan(hid: 0x28) == 0x1C && EnterTrace.pcScan(hid: 0x58) == 0xE01C)
assert(EnterTrace.verdict(pressed: true, focused: true, postedBefore: false, postedAfter: true) == "posted down to Wine")
assert(EnterTrace.verdict(pressed: true, focused: false, postedBefore: false, postedAfter: false) == "NOT posted: keyboard focus is elsewhere")
assert(EnterTrace.verdict(pressed: true, focused: true, postedBefore: false, postedAfter: false).hasPrefix("NOT posted: held back"))
assert(EnterTrace.verdict(pressed: true, focused: true, postedBefore: true, postedAfter: true).hasPrefix("not posted: Enter was already down"))
assert(EnterTrace.verdict(pressed: false, focused: true, postedBefore: true, postedAfter: false) == "posted up to Wine")
assert(EnterTrace.verdict(pressed: false, focused: false, postedBefore: false, postedAfter: false) == "nothing to release: its down was never posted")
assert(EnterTrace.uikitLine(view: "V", text: "abc", ignored: false) == nil)
assert(EnterTrace.uikitLine(view: "MetalBackedView", text: "\n", ignored: true)!.hasPrefix("[enter] uikit-text MetalBackedView newline -> ignored"))
assert(EnterTrace.uikitLine(view: "LibraryKeyInput", text: "a\r", ignored: false)!.contains("posted as VK_RETURN"))
print("PASS: EnterTrace kinds, PC scan codes, verdicts and the text bridges' newline line")
'''
swiftc = os.environ.get('SWIFTC', 'swiftc')
if shutil.which(swiftc):
    with tempfile.TemporaryDirectory(prefix='bcd-enter-trace-swift-') as temp:
        temp = Path(temp)
        (temp / 'main.swift').write_text('import Foundation\n' + swift)
        r = subprocess.run([swiftc, str(temp / 'main.swift'), '-o', str(temp / 'swift-test')], capture_output=True, text=True)
        check('EnterTrace compiles', r.returncode == 0, r.stderr[-3000:])
        if r.returncode == 0:
            r = subprocess.run([str(temp / 'swift-test')], capture_output=True, text=True)
            print(r.stdout, end='')
            check('the Swift checks pass', r.returncode == 0, r.stderr[-2000:])
elif args.require_swift:
    check('a Swift compiler is at hand (--require-swift)', False, f'{swiftc} not found')
else:
    print('SKIP: Swift compiler unavailable locally; macOS CI must run this check with --require-swift')

# ---- source: where the trace sits, and that nothing else changed ---------------------------------------------------
pure_end = hardware.index('// MARK: - Device glue')
check('EnterTrace is in the pure section (Foundation only, compiled on its own)', hardware.index('enum EnterTrace {') < pure_end)
key = method(hardware, '    private func key(_ code: GCKeyCode, _ pressed: Bool) {')
check('the hardware key is traced as GCKeyboard delivers it, before the key map, the focus refresh and the gate',
      key.index('EnterTrace.isEnter(hid: code.rawValue)') < key.index('guard let vk = HardwareKeyMap.vk(forHIDUsage: code.rawValue)')
      < key.index('refreshFocus("key")') < key.index('keys.press(vk, focused: keyboardFocused)'), key[:600])
check('...and its outcome when key() returns (a defer: every return path)', 'defer {' in key and 'EnterTrace.verdict(' in key)
sync = method(hardware, '    private func syncKeys() {')
check('syncKeys posts the same edges at once; VK_RETURN only names its HID usage (winios_post_key_hid)',
      'let edges = keysPosted.update(keys.wanted(focused: keyboardFocused).subtracting(deferredCommands))' in sync
      and 'winios_post_key_hid(vk, 0, Int32(lastEnterHID))' in sync and 'winios_post_key_hid(vk, 1, Int32(lastEnterHID))' in sync
      and 'winios_post_key(vk, 0)' in sync and 'winios_post_key(vk, 1)' in sync and 'minuteKeys += edges.down.count' in sync, sync)
for name, body in [('key()', key), ('syncKeys()', sync)]:
    check(f'{name} waits for nothing (no timer, no asyncAfter, no sleep)',
          not any(w in body for w in ('asyncAfter', 'Timer(', 'usleep', 'Thread.sleep')), body)
check('the trace only writes the log (fputs), it posts nothing',
      'winios_post' not in method(hardware, '    private func traceEnter(_ s: String) {')
      and 'winios_post' not in method(hardware, '    static func traceEnterText(view: String, text: String, ignored: Bool) {'))
mbv = between(content, '    func insertText(_ text: String) {', '    func deleteBackward() {')
check('the game view text bridge: traced before its own hardware-keyboard check, which still returns as before',
      mbv.index('HardwareInput.traceEnterText(view: "MetalBackedView"') < mbv.index('if HardwareInput.shared.handlesTyping { return }'), mbv)
lki = between(library, '    func insertText(_ text: String) {', '    func deleteBackward()')
check('the key-window text bridge is traced and posts as before',
      'HardwareInput.traceEnterText(view: "LibraryKeyInput", text: text, ignored: false)' in lki and 'press(vk)' in lki, lki)
post = function(winios, 'void winios_post_key_hid(int vk, int down, int hid) {')
check('Winios.m: any other key is queued exactly as before (data 0)',
      'if (vk != WINIOS_ENTER_VK) {\n        winios_q_push_ev(WINIOS_EV_KEY, vk, 0, down ? 0 : KEYEVENTF_KEYUP, 0);' in post, post)
check('Winios.m: winios_post_key is winios_post_key_hid with no HID usage',
      'void winios_post_key(int vk, int down) {\n    winios_post_key_hid(vk, down, 0);\n}' in winios)
key_drv = function(driver, 'void winios_drv_post_key(unsigned short vk, unsigned int flags)\n{')
check('driver: the key is sent as before, then (VK_RETURN only) traced',
      key_drv.count('send_hardware_message(') == 1
      and key_drv.index('send_hardware_message(') < key_drv.index('if (vk == VK_RETURN) winios_enter_trace_sent( flags, scan, st );'), key_drv)
traced = function(driver, 'void winios_drv_post_key_traced(unsigned short vk, unsigned int flags, unsigned int enter_seq, unsigned int enter_hid)\n{')
check('driver: the traced entry only sets the number around winios_drv_post_key',
      'winios_drv_post_key( vk, flags );' in traced and 'send_hardware_message' not in traced, traced)
added = (post.split('if (vk != WINIOS_ENTER_VK) {', 1)[1] + traced
         + function(driver, 'static void winios_enter_trace_sent( UINT flags, UINT scan, NTSTATUS st )\n{') + function(hardware, 'enum EnterTrace {')
         + method(hardware, '    private func traceEnter(_ s: String) {'))
check('no IME, DirectInput or setting is read or touched by the trace',
      not any(w in added for w in ('Imm', 'dinput', 'getenv', 'MadeiraConfig', 'UserDefaults')))
ci = (root / '.github/workflows/build-ipa.yml').read_text()
check('CI runs this check with --require-swift', 'python3 tests/host/check-enter-trace.py --require-swift' in ci)

if failures:
    print(f'check-enter-trace: {failures} FAILED')
    sys.exit(1)
print('check-enter-trace: all passed')
