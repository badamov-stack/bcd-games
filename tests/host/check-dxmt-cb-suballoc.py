#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright 2026 thebcd69 (BCD)
# BCD Material: additional terms under GPL-3.0 section 7 apply; see LICENSE-BCD.md.
"""DXMT_CB_SUBALLOC (tools/patch-d3d11-src-cb-suballoc.py): DEFAULT constant buffers suballocated from one page in named programs,
d3d11-src.dll only. No Wine runs; the helpers the patch adds are compiled with stubs (C++ compiler needed).

  - the gate: only Usage DEFAULT, BindFlags exactly D3D11_BIND_CONSTANT_BUFFER, MiscFlags 0 and ByteWidth 1..4096;
  - the switch: off unset, empty, 0, 1 and *; on only for the program's own file name (case-insensitive, ';' or ',' lists), with
    its line once; a value naming another program says so and stays off;
  - the edit (on a copy of the pinned dxmt/src, when one is at hand: the submodule or DXMT_SRC_DIR): it applies, a second run
    changes nothing, it only adds lines, the DYNAMIC branch and the allocation are as they were, the new flag is set only inside
    the switch's branch and before the first allocation (so the DynamicBuffer gets it too); a moved anchor exits 1, file unchanged;
  - the wiring: in tools/build-d3d11-dll.sh's BCD_PATCHES with its marker, before patch-d3d11-src-all-arch.py (last); never run on
    the submodule by the workflow; outside the i386 farm's tools/patch-dxmt-*.py cache key; no list, auto-tune rule or bcd.cfg
    default sets the key.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

R = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = R / "tools/patch-d3d11-src-cb-suballoc.py"
SRC = pathlib.Path(os.environ.get("DXMT_SRC_DIR", R / "dxmt")) / "src"
ok = True


def check(what, cond, detail=""):
    global ok
    print(("ok   " if cond else "FAIL ") + what + ("" if cond or not detail else f": {detail}"))
    ok &= bool(cond)


script = SCRIPT.read_text()
check("the patch script exists", SCRIPT.is_file())

# ---- the helpers, compiled with stubs -------------------------------------------------------------------------------------
helpers = script.split("HELPERS = r'''namespace dxmt {\n", 1)[1].split("'''", 1)[0]
pure = helpers.split("/* cb-suballoc pure begin */", 1)[1].split("/* cb-suballoc pure end */", 1)[0]
here = helpers.split("/* cb-suballoc pure end */", 1)[1]
cxx = os.environ.get("CXX", shutil.which("c++") or shutil.which("g++") or shutil.which("clang++") or "c++")
prog = r'''
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
typedef unsigned int UINT;
enum { D3D11_USAGE_DEFAULT = 0, D3D11_USAGE_IMMUTABLE = 1, D3D11_USAGE_DYNAMIC = 2, D3D11_USAGE_STAGING = 3 };
enum { D3D11_BIND_VERTEX_BUFFER = 0x1, D3D11_BIND_INDEX_BUFFER = 0x2, D3D11_BIND_CONSTANT_BUFFER = 0x4,
       D3D11_BIND_SHADER_RESOURCE = 0x8, D3D11_BIND_UNORDERED_ACCESS = 0x80 };
namespace env {
std::string getEnvVar(const char *n) { const char *v = getenv(n); return v ? v : ""; }
std::string getExeName() { const char *v = getenv("TEST_EXE"); return v ? v : ""; }
}
static int warns;
#define WARN(...) do { warns++; std::printf("WARN:"); print_all(__VA_ARGS__); std::printf("\n"); } while (0)
static void print_one(const std::string &s) { std::printf("%s", s.c_str()); }
static void print_one(const char *s) { std::printf("%s", s); }
static void print_one(unsigned v) { std::printf("%u", v); }
static void print_one(int v) { std::printf("%d", v); }
static void print_all() {}
template <typename A, typename... T> static void print_all(A &&a, T &&...t) { print_one(a); print_all(t...); }
''' + pure + here + r'''
int main(int argc, char **argv) {
  if (argc > 1 && !strcmp(argv[1], "here")) {  /* call first: the order of printf's arguments is unspecified */
    const int h1 = madeiraCbSuballocHere() ? 1 : 0; const int w1 = warns;
    const int h2 = madeiraCbSuballocHere() ? 1 : 0; const int w2 = warns;
    std::printf("here=%d warns=%d\nagain=%d warns=%d\n", h1, w1, h2, w2); return 0;
  }
  int bad = 0;
#define T(c) do { if (!(c)) { std::printf("FAILED: %s\n", #c); bad++; } } while (0)
  T(madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER, 0, 16));
  T(madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER, 0, 256));
  T(madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER, 0, 4096));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER, 0, 4097));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER, 0, 65536));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER, 0, 0));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DYNAMIC, D3D11_BIND_CONSTANT_BUFFER, 0, 16));     /* DYNAMIC: its own path, unchanged */
  T(!madeiraCbSuballocFits(D3D11_USAGE_IMMUTABLE, D3D11_BIND_CONSTANT_BUFFER, 0, 16));
  T(!madeiraCbSuballocFits(D3D11_USAGE_STAGING, D3D11_BIND_CONSTANT_BUFFER, 0, 16));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER | D3D11_BIND_SHADER_RESOURCE, 0, 16));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_VERTEX_BUFFER, 0, 16));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_SHADER_RESOURCE, 0, 16));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_UNORDERED_ACCESS, 0, 16));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, 0, 0, 16));
  T(!madeiraCbSuballocFits(D3D11_USAGE_DEFAULT, D3D11_BIND_CONSTANT_BUFFER, 0x20, 16));  /* any MiscFlags: off */
  T(madeiraCbSuballocNamed("DevilMayCry5.exe", "DevilMayCry5.exe"));
  T(madeiraCbSuballocNamed("devilmaycry5.EXE", "DevilMayCry5.exe"));
  T(madeiraCbSuballocNamed("Launcher.exe; DevilMayCry5.exe", "DevilMayCry5.exe"));
  T(madeiraCbSuballocNamed("a.exe,DevilMayCry5.exe,", "DevilMayCry5.exe"));
  T(!madeiraCbSuballocNamed("DevilMayCry5", "DevilMayCry5.exe"));
  T(!madeiraCbSuballocNamed("1", "DevilMayCry5.exe"));
  T(!madeiraCbSuballocNamed("*", "DevilMayCry5.exe"));
  T(!madeiraCbSuballocNamed("0", "DevilMayCry5.exe"));
  T(!madeiraCbSuballocNamed("", "DevilMayCry5.exe"));
  T(!madeiraCbSuballocNamed(";;", "DevilMayCry5.exe"));
  T(!madeiraCbSuballocNamed("DevilMayCry5.exe", "re7.exe"));
  T(!madeiraCbSuballocNamed("DevilMayCry5.exe", ""));
  madeiraCbSuballocNote(16); madeiraCbSuballocNote(256);
  std::printf(bad ? "BAD %d\n" : "PURE OK\n", bad);
  return bad != 0;
}
'''
with tempfile.TemporaryDirectory(prefix="bcd-cb-suballoc-") as tmp:
    tmp = pathlib.Path(tmp)
    (tmp / "t.cpp").write_text(prog)
    r = subprocess.run([cxx, "-std=c++17", "-Wall", "-Werror", "-Wno-unused-function", str(tmp / "t.cpp"), "-o", str(tmp / "t")],
                       capture_output=True, text=True)
    check("the helpers the patch adds compile (C++17, -Wall -Werror)", r.returncode == 0, r.stderr[-1500:])
    if r.returncode == 0:
        r = subprocess.run([str(tmp / "t")], capture_output=True, text=True)
        check("the gate takes only DEFAULT, BindFlags == CONSTANT_BUFFER, MiscFlags 0, ByteWidth 1..4096; names match exactly",
              r.returncode == 0 and "PURE OK" in r.stdout, r.stdout[-1500:])
        check("the note line: the first buffers name their ByteWidth and names per page (16 for 16 and 256 bytes)",
              "#1 ByteWidth=16 names per page=16" in r.stdout and "#2 ByteWidth=256 names per page=16" in r.stdout, r.stdout[-600:])

        def here_run(value, exe="DevilMayCry5.exe"):
            e = {k: v for k, v in os.environ.items() if k != "DXMT_CB_SUBALLOC"}
            if value is not None:
                e["DXMT_CB_SUBALLOC"] = value
            e["TEST_EXE"] = exe
            return subprocess.run([str(tmp / "t"), "here"], capture_output=True, text=True, env=e).stdout

        out = here_run(None)
        check("unset: off, and nothing is logged", "here=0 warns=0" in out and "again=0 warns=0" in out, out)
        for v in ("", "0", "1", "*"):
            out = here_run(v)
            check(f"DXMT_CB_SUBALLOC={v!r}: off (only a program's own name turns it on)", "here=0" in out and "again=0" in out, out)
        out = here_run("DevilMayCry5.exe")
        check("DXMT_CB_SUBALLOC=DevilMayCry5.exe in DevilMayCry5.exe: on, its line once (read once per process)",
              "here=1 warns=1" in out and "again=1 warns=1" in out
              and "[cb-suballoc] madeira-bcd: DevilMayCry5.exe: DEFAULT constant buffers of up to 4096 bytes suballocate" in out, out)
        out = here_run("DevilMayCry5.exe", exe="re7.exe")
        check("the same line in another program (re7.exe): off, and it says so once",
              "here=0 warns=1" in out and "does not name re7.exe: off" in out, out)

# ---- the edit, on a copy of the pinned sources ----------------------------------------------------------------------------
orig_file = SRC / "d3d11/d3d11_buffer.cpp"
if not orig_file.is_file():
    print(f"SKIP: no dxmt sources at {SRC} (check out the dxmt submodule or set DXMT_SRC_DIR); the edit checks need them")
else:
    with tempfile.TemporaryDirectory(prefix="bcd-cb-suballoc-src-") as tmp:
        tmp = pathlib.Path(tmp)
        d = tmp / "dxmt/src/d3d11"
        d.mkdir(parents=True)
        f = d / "d3d11_buffer.cpp"
        shutil.copy(orig_file, f)
        before = f.read_text()
        r1 = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True)
        after = f.read_text()
        r2 = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True)
        check("it applies to the pinned d3d11_buffer.cpp (run where dxmt/ is the copy, as tools/build-d3d11-dll.sh does)",
              r1.returncode == 0 and after != before, r1.stdout + r1.stderr)
        check("a second run changes nothing", r2.returncode == 0 and "already patched" in r2.stdout and f.read_text() == after,
              r2.stdout + r2.stderr)
        import difflib
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0))
        removed = [l for l in diff if l.startswith("-") and not l.startswith("---")]
        check("it only adds lines (nothing of the original is removed or changed)", not removed, "\n".join(removed[:5]))
        dyn = ("    } else {\n      flags.set(BufferAllocationFlag::SuballocateFromOnePage);\n#ifdef __i386__\n"
               "      flags.set(BufferAllocationFlag::CpuPlaced);\n#endif\n    }\n")
        check("the DYNAMIC branch is unchanged", dyn in before and dyn in after)
        gate_at = after.find("    if (madeiraCbSuballocFits(pDesc->Usage, pDesc->BindFlags, pDesc->MiscFlags, pDesc->ByteWidth) &&")
        alloc_at = after.find('    auto allocation = buffer_->allocate(flags, "d3d11_buffer:CreateBuffer");')
        dyn_at = after.find("      dynamic_ = new DynamicBuffer(buffer_.ptr(), flags);")
        check("the gate sits after the original flags and before the first allocation and the DynamicBuffer (both get the flag)",
              after.find(dyn) < gate_at < alloc_at < dyn_at and gate_at > 0)
        gate = after[gate_at:alloc_at]
        check("the new flag is set only inside the switch's branch",
              gate.count("flags.set(BufferAllocationFlag::SuballocateFromOnePage);") == 1
              and "madeiraCbSuballocHere()) {" in gate and gate.rstrip().endswith("}"))
        check("no new i386 gate (patch-d3d11-src-all-arch.py counts them)", after.count("__i386__") == before.count("__i386__"))
        check("the marker tools/build-d3d11-dll.sh looks for is in the source", "[cb-suballoc] madeira-bcd" in after)
        # a moved anchor: exit 1, the file as it was
        f.write_text(before.replace('"d3d11_buffer:CreateBuffer"', '"d3d11_buffer:CreateBuffer2"'))
        moved = f.read_text()
        r3 = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True)
        check("a moved anchor exits 1 and leaves the file as it was", r3.returncode == 1 and f.read_text() == moved,
              r3.stdout + r3.stderr)

# ---- the wiring --------------------------------------------------------------------------------------------------------------
sh = (R / "tools/build-d3d11-dll.sh").read_text()
m = re.search(r"\nBCD_PATCHES=\((.*?)\)\n", sh, re.S)
pairs = re.findall(r'"([^"]+\.py)" "((?:[^"\\]|\\.)*)"', m.group(1)) if m else []
names = [p for p, _ in pairs]
check("BCD_PATCHES has patch-d3d11-src-cb-suballoc.py with its marker",
      ("patch-d3d11-src-cb-suballoc.py", "[cb-suballoc] madeira-bcd") in pairs)
check("...once, and before patch-d3d11-src-all-arch.py, which stays last",
      names.count("patch-d3d11-src-cb-suballoc.py") == 1 and names[-1] == "patch-d3d11-src-all-arch.py"
      and names.index("patch-d3d11-src-cb-suballoc.py") < names.index("patch-d3d11-src-all-arch.py"))
wf = "".join(p.read_text() for p in (R / ".github/workflows").glob("*.yml"))
check("no workflow runs it on the submodule (the 32-bit DLLs never get it)", "patch-d3d11-src-cb-suballoc" not in wf)
check("its name stays outside the i386 farm's cache key (tools/patch-dxmt-*.py)", not SCRIPT.name.startswith("patch-dxmt-"))
recs = (R / "recommended/recommendations.json").read_text()
rules = (R / "build/tools/autotune_rules.py").read_text()
check("no recommended list and no auto-tune rule sets DXMT_CB_SUBALLOC (off for every game until a line names one)",
      "DXMT_CB_SUBALLOC" not in recs and "DXMT_CB_SUBALLOC" not in rules)
app = "".join(p.read_text(errors="replace") for p in (R / "app/Madeira").glob("*.swift"))
app += "".join(p.read_text(errors="replace") for p in (R / "app/Madeira").glob("*.m"))
check("the app sets nothing for it (no default, no bcd.cfg line)", "DXMT_CB_SUBALLOC" not in app)

print("PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
