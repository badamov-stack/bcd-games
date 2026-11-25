#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright 2026 thebcd69 (BCD)
# BCD Material: additional terms under GPL-3.0 section 7 apply; see LICENSE-BCD.md.
"""DEFAULT constant buffers suballocated from one page in named programs (DXMT_CB_SUBALLOC), d3d11-src.dll only.

Devil May Cry 5 (Steam 601150, build 721, iPad15,5, 2026-11-25): in its tessellated scenes one game thread ran at 97-99% of a core
while the GPU was about half busy, half of the thread's samples in d3d11.dll. A 16-byte constant buffer was replaced 1,000-3,850 times
a frame with UpdateSubresource ([dyn-census] #6). The game's constant buffers are D3D11_USAGE_DEFAULT: their names carry GpuManaged
("buffer flags n[GpuManaged]=1524202" for 1,521,854 DynamicBuffer::allocate names) and only 2 buffers had SuballocateFromOnePage.

Why that costs: a full-buffer UpdateSubresource is a Map(WRITE_DISCARD) (d3d11_context_impl.cpp UpdateSubresource1), and
MapDynamicBuffer (d3d11_context_imm.cpp, d3d11_context_def.cpp) first takes the next suballocation of the current name. D3D11Buffer's
constructor (d3d11_buffer.cpp) gives SuballocateFromOnePage to D3D11_USAGE_DYNAMIC buffers only, so a DEFAULT buffer's name has one
suballocation and every update takes DynamicBuffer::allocate (its lock and fifo, a new Metal buffer when nothing is reusable),
updateImmediateName and a rename. A DYNAMIC buffer of the same size takes that path once per 16 updates (4096 / 256).

DXMT_CB_SUBALLOC = <program>;<program> (program file names, case-insensitive, ';' or ','): in those programs a buffer created with
Usage == D3D11_USAGE_DEFAULT, BindFlags == D3D11_BIND_CONSTANT_BUFFER (that flag alone), MiscFlags == 0 and ByteWidth <= 4096 gets
SuballocateFromOnePage too, as a DYNAMIC buffer already does. Its names are then one page with up to 16 parts (BufferAllocation), the
fifo recycles whole pages exactly as for DYNAMIC buffers, and every reader adds currentSuballocationOffset() (ArgumentEncodingContext::
access: constant, vertex, SRV/UAV bindings, copies, indirect arguments). Only a program's own file name turns it on: unset, empty, 0,
1 and * leave it off, so the line cannot reach another game through bcd.cfg. Read once per process.

Lines: "[cb-suballoc] madeira-bcd: <exe>: DEFAULT constant buffers of up to 4096 bytes suballocate from one page (DXMT_CB_SUBALLOC)"
once when it is on, "... DXMT_CB_SUBALLOC=<value> does not name <exe>: off" once when the value names another program, and
"[cb-suballoc] madeira-bcd #<n> ByteWidth=<w> names per page=<k>" for the first 4 buffers it changes, then every 1024th.
tools/build-d3d11-dll.sh looks for "[cb-suballoc] madeira-bcd" in the DLL it builds (BCD_PATCHES).

Applied by tools/build-d3d11-dll.sh to its COPY of dxmt/src (it runs the script in a directory whose "dxmt" is the copy); the
submodule is not modified, and the name stays outside the i386 farm's tools/patch-dxmt-*.py cache key: no 32-bit DLL gets it.
Without the switch every buffer gets the flags it got before (the new branch only adds a flag when it is on).
Idempotent (marker below); an anchor that moved exits 1 with the file left as it was. tests/host/check-dxmt-cb-suballoc.py checks it.

Usage: patch-d3d11-src-cb-suballoc.py [<dxmt/src>]   (default: dxmt/src under the current directory)
"""
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dxmt/src")
FILE = ROOT / "d3d11" / "d3d11_buffer.cpp"
MARKER = "madeira-bcd: [cb-suballoc]"

INCLUDE_OLD = '#include "d3d11_resource.hpp"\n'
INCLUDE_NEW = ('#include "d3d11_resource.hpp"\n'
               '#include "util_env.hpp"   /* madeira-bcd: [cb-suballoc] DXMT_CB_SUBALLOC */\n'
               '#include <algorithm>\n'
               '#include <atomic>\n'
               '#include <string>\n')

NAMESPACE_OLD = "namespace dxmt {\n"
HELPERS = r'''namespace dxmt {

/* madeira-bcd: [cb-suballoc] DEFAULT constant buffers suballocated from one page (tools/patch-d3d11-src-cb-suballoc.py; Devil May
 * Cry 5, build 721). A full-buffer UpdateSubresource is a Map(WRITE_DISCARD); with one suballocation per name every update takes
 * DynamicBuffer::allocate and a rename. DXMT_CB_SUBALLOC = <program>;<program> (file names, case-insensitive): in those programs a
 * DEFAULT buffer bound only as a constant buffer, MiscFlags 0, ByteWidth <= 4096, suballocates from one page as a DYNAMIC buffer
 * does. Only a program's own name turns it on (not 1 or *). Read once per process. */
/* cb-suballoc pure begin */
static bool
madeiraCbSuballocFits(UINT usage, UINT bind_flags, UINT misc_flags, UINT byte_width) {
  return usage == D3D11_USAGE_DEFAULT && bind_flags == D3D11_BIND_CONSTANT_BUFFER && misc_flags == 0 && byte_width != 0 &&
         byte_width <= 4096;
}

static bool
madeiraCbSuballocNamed(const std::string &list, const std::string &exe) {
  auto lower = [](std::string s) {
    for (auto &c : s)
      if (c >= 'A' && c <= 'Z')
        c += 'a' - 'A';
    return s;
  };
  const std::string want = lower(exe);
  if (want.empty())
    return false;
  for (size_t i = 0; i <= list.size();) {
    size_t j = list.find_first_of(";,", i);
    if (j == std::string::npos)
      j = list.size();
    std::string item = list.substr(i, j - i);
    const size_t a = item.find_first_not_of(" \t");
    item = a == std::string::npos ? std::string() : item.substr(a, item.find_last_not_of(" \t") - a + 1);
    if (!item.empty() && lower(item) == want)
      return true;
    i = j + 1;
  }
  return false;
}
/* cb-suballoc pure end */

static bool
madeiraCbSuballocHere() {
  static const bool here = [] {
    const std::string list = env::getEnvVar("DXMT_CB_SUBALLOC");
    if (list.empty())
      return false;
    const std::string exe = env::getExeName();
    const bool hit = madeiraCbSuballocNamed(list, exe);
    if (hit)
      WARN("[cb-suballoc] madeira-bcd: ", exe,
           ": DEFAULT constant buffers of up to 4096 bytes suballocate from one page (DXMT_CB_SUBALLOC)");
    else
      WARN("[cb-suballoc] madeira-bcd: DXMT_CB_SUBALLOC=", list, " does not name ", exe, ": off");
    return hit;
  }();
  return here;
}

static void
madeiraCbSuballocNote(UINT byte_width) {
  static std::atomic<uint32_t> count{0};
  const uint32_t n = count.fetch_add(1, std::memory_order_relaxed) + 1;
  if (n <= 4 || (n & 1023) == 0)
    WARN("[cb-suballoc] madeira-bcd #", n, " ByteWidth=", byte_width, " names per page=",
         4096u / std::max<UINT>(256u, (byte_width + 15u) & ~15u));
}
'''

GATE_OLD = '    auto allocation = buffer_->allocate(flags, "d3d11_buffer:CreateBuffer");\n'
GATE_NEW = ('    /* madeira-bcd: [cb-suballoc] (DXMT_CB_SUBALLOC): a DEFAULT constant buffer the program replaces with UpdateSubresource\n'
            '     * renames like a DYNAMIC one; in a named program it suballocates from one page as a DYNAMIC one does. Off: unchanged. */\n'
            '    if (madeiraCbSuballocFits(pDesc->Usage, pDesc->BindFlags, pDesc->MiscFlags, pDesc->ByteWidth) &&\n'
            '        madeiraCbSuballocHere()) {\n'
            '      flags.set(BufferAllocationFlag::SuballocateFromOnePage);\n'
            '      madeiraCbSuballocNote(pDesc->ByteWidth);\n'
            '    }\n'
            + GATE_OLD)

EDITS = [
    ("the env helper include after d3d11_resource.hpp", INCLUDE_OLD, INCLUDE_NEW),
    ("the helpers at the start of namespace dxmt", NAMESPACE_OLD, HELPERS),
    ("the gate before the constructor's first allocation", GATE_OLD, GATE_NEW),
]


def main():
    if not FILE.is_file():
        sys.exit(f"{FILE}: not found")
    text = FILE.read_text()
    if MARKER in text:
        print(f"{FILE}: already patched")
        return
    out = text
    for what, old, new in EDITS:
        n = out.count(old)
        if n != 1:
            sys.exit(f"{FILE}: anchor for {what} found {n} times (want 1); file left as it was")
        out = out.replace(old, new, 1)
    FILE.write_text(out)
    print(f"{FILE}: DEFAULT constant buffers suballocate in the programs DXMT_CB_SUBALLOC names (off by default)")


if __name__ == "__main__":
    main()
