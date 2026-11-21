#!/usr/bin/env python3
"""
Overlay native build for ONLYOFFICE Desktop Editors (Linux & Windows).

Rebuilds only the patched components against sources already staged in WORK_DIR:
  - ICU, Boost, CryptoPP, CompoundFile (cached deps)
  - hunspell headers
  - ascdocumentscore + qtascdocumentscore (desktop-sdk)
  - DesktopEditors executable (desktop-apps/win-linux, ASCDocumentEditor.pro)

Unchanged core binaries/resources are staged from the official package
(or the official CEF binary archive on Windows, where import .libs are needed).

Usage:
  build_overlay_desktop.py <work_dir> <official_pkg_dir> <qt_parent_dir> <platform> [vs_path]

  <official_pkg_dir> : extracted official package root containing the app files
                       (linux: .../opt/onlyoffice/desktopeditors, win: dir with editors.exe)
  <platform>         : linux_64 | linux_arm64 | win_64
  [vs_path]          : path to VC/Auxiliary/Build (Windows only)
"""
import glob
import os
import re
import shutil
import subprocess
import sys

WORK_DIR = os.path.abspath(sys.argv[1])
PKG_DIR = os.path.abspath(sys.argv[2])
QT_PARENT_DIR = os.path.abspath(sys.argv[3])
PLAT = sys.argv[4]
VS_PATH = sys.argv[5] if len(sys.argv) > 5 else ""

IS_WIN = PLAT.startswith("win")
IS_LINUX = PLAT.startswith("linux")

BT = os.path.join(WORK_DIR, "build_tools")
CORE = os.path.join(WORK_DIR, "core")
SDK = os.path.join(WORK_DIR, "desktop-sdk")
APPS = os.path.join(WORK_DIR, "desktop-apps")

LIB_PLAT = os.path.join(CORE, "build", "lib", PLAT)
BIN_PLAT = os.path.join(CORE, "build", "bin", PLAT)
CEF_PLAT = os.path.join(CORE, "Common", "3dParty", "cef", PLAT, "build")


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def write_config():
    lines = [
        'update="0"',
        'branch="master"',
        'clean="0"',
        'module="core desktop"',
        'develop="0"',
        'beta="0"',
        f'platform="{PLAT}"',
        f'qt-dir="{QT_PARENT_DIR}"',
        'no-apps="0"',
        'multiprocess="1"',
        'sysroot="0"',
    ]
    if VS_PATH:
        lines.append(f'vs-path="{VS_PATH}"')
    with open(os.path.join(BT, "config"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


write_config()

for sub in ["scripts", "scripts/develop", "scripts/develop/vendor", "scripts/core_common", "scripts/core_common/modules"]:
    sys.path.append(os.path.join(BT, sub))

os.chdir(BT)
import config
import base
import boost
import hunspell
import qmake

config.parse()
base.check_python()
base.set_env("BUILD_PLATFORM", PLAT)
config.parse_defaults()
base.check_build_version(BT)
base.configure_common_apps()
ver = base.get_env("PRODUCT_VERSION") or "10.0.0"
config.extend_option("qmake_addon", f"URL_WEBAPPS_HELP=https://download.onlyoffice.com/install/desktop/editors/help/v{ver}/apps")

# ---------------------------------------------------------------------------
# 1. Stage prebuilt binaries from the official package into core/build + cef
# ---------------------------------------------------------------------------
os.makedirs(LIB_PLAT, exist_ok=True)
os.makedirs(BIN_PLAT, exist_ok=True)
os.makedirs(CEF_PLAT, exist_ok=True)

if IS_LINUX:
    # Package root holds lib*.so + cef runtime; converter/ holds core .so set.
    for so in glob.glob(os.path.join(PKG_DIR, "*.so*")) + glob.glob(os.path.join(PKG_DIR, "converter", "*.so*")):
        dst = os.path.join(LIB_PLAT, os.path.basename(so))
        if not os.path.exists(dst):
            shutil.copy2(so, dst)
    # CEF runtime (libcef.so + resources) -> link & runtime staging dir
    cef_names = [
        "libcef.so", "icudtl.dat", "snapshot_blob.bin", "v8_context_snapshot.bin",
        "chrome-sandbox", "libEGL.so", "libGLESv2.so", "libvk_swiftshader.so",
        "libvulkan.so.1", "vk_swiftshader_icd.json", "chrome_100_percent.pak",
        "chrome_200_percent.pak", "resources.pak", "locales",
    ]
    for name in cef_names:
        src = os.path.join(PKG_DIR, name)
        dst = os.path.join(CEF_PLAT, name)
        if not os.path.exists(src):
            continue
        if os.path.isdir(src):
            if not os.path.exists(dst):
                shutil.copytree(src, dst, symlinks=True)
        elif not os.path.exists(dst):
            shutil.copy2(src, dst)
else:
    # Windows: stage all runtime dlls into lib dir (import .libs are generated below)
    for dll in glob.glob(os.path.join(PKG_DIR, "*.dll")) + glob.glob(os.path.join(PKG_DIR, "converter", "*.dll")):
        dst = os.path.join(LIB_PLAT, os.path.basename(dll))
        if not os.path.exists(dst):
            shutil.copy2(dll, dst)
    # exe helpers (editors_helper.exe lives in core build/bin)
    for exe in glob.glob(os.path.join(PKG_DIR, "*.exe")):
        dst = os.path.join(BIN_PLAT, os.path.basename(exe))
        if not os.path.exists(dst):
            shutil.copy2(exe, dst)

# ---------------------------------------------------------------------------
# 2. CEF for Windows: official package ships no import libs -> use the official
#    binary archive (contains libcef.lib, libcef.dll, resources).
# ---------------------------------------------------------------------------
if IS_WIN and not os.path.isfile(os.path.join(CEF_PLAT, "libcef.lib")):
    print("== Fetching official CEF binary (win_64, 5414) ==")
    cef_url = "https://github.com/ONLYOFFICE-data/build_tools_data/raw/refs/heads/master/cef/5414/win_64/cef_binary.7z"
    cef_arc = os.path.join(CORE, "Common", "3dParty", "cef", "cef_binary_win_64.7z")
    os.makedirs(os.path.dirname(cef_arc), exist_ok=True)
    run(["curl", "-fL", "--retry", "3", "-o", cef_arc, cef_url])
    tmp = os.path.join(CORE, "Common", "3dParty", "cef", "_win_extract")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    run(["7z", "x", cef_arc, f"-o{tmp}", "-y"])
    # archive layout: <tmp>/Release, <tmp>/Resources (plus sources); merge into build/
    for sub in ["Release", "Resources"]:
        d = os.path.join(tmp, sub)
        if os.path.isdir(d):
            for it in os.listdir(d):
                s = os.path.join(d, it)
                t = os.path.join(CEF_PLAT, it)
                if os.path.isdir(s):
                    if not os.path.exists(t):
                        shutil.copytree(s, t)
                elif not os.path.exists(t):
                    shutil.copy2(s, t)
    # fallback: flat layout
    for it in os.listdir(tmp):
        s = os.path.join(tmp, it)
        t = os.path.join(CEF_PLAT, it)
        if os.path.isfile(s) and not os.path.exists(t):
            shutil.copy2(s, t)
    shutil.rmtree(tmp, ignore_errors=True)
    os.remove(cef_arc)

# ---------------------------------------------------------------------------
# 3. Windows: generate MSVC import .lib files for every staged official .dll
#    (dumpbin /exports -> .def -> lib /def:). Our own rebuilt dlls produce
#    their .lib during qmake build, so generate first, build later.
# ---------------------------------------------------------------------------
if IS_WIN:
    machine = "x64" if PLAT == "win_64" else "arm64"
    for dll in glob.glob(os.path.join(LIB_PLAT, "*.dll")):
        lib = dll[:-4] + ".lib"
        if os.path.exists(lib):
            continue
        name = os.path.basename(dll)
        print(f"== Generating import lib: {name} ==")
        out = subprocess.run(["dumpbin", "/exports", dll], capture_output=True, text=True).stdout
        exports = []
        in_table = False
        for ln in out.splitlines():
            if in_table:
                m = re.match(r"\s+\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+(\S+)", ln)
                if m:
                    exports.append(m.group(1))
                elif ln.strip() == "" and exports:
                    break
            elif "ordinal" in ln and "name" in ln:
                in_table = True
        if not exports:
            print(f"  !! no exports parsed for {name}, skipping")
            continue
        def_file = dll[:-4] + ".def"
        with open(def_file, "w", encoding="utf-8") as f:
            f.write(f"LIBRARY {name}\nEXPORTS\n")
            f.writelines(f"  {e}\n" for e in exports)
        subprocess.run(["lib", f"/def:{def_file}", f"/machine:{machine}", f"/out:{lib}"], check=True)
        os.remove(def_file)

# ---------------------------------------------------------------------------
# 4. ICU 74.2
# ---------------------------------------------------------------------------
icu_root = os.path.join(CORE, "Common", "3dParty", "icu")


def icu_src_dir():
    icu_src = os.path.join(icu_root, "icu")
    if not os.path.isdir(icu_src):
        os.makedirs(icu_root, exist_ok=True)
        tmp_clone = os.path.join(icu_root, "icu_tmp")
        shutil.rmtree(tmp_clone, ignore_errors=True)
        run(["git", "clone", "--depth", "1", "--branch", "release-74-2",
             "https://github.com/unicode-org/icu.git", tmp_clone])
        shutil.move(os.path.join(tmp_clone, "icu4c"), icu_src)
        icu_lic = os.path.join(tmp_clone, "LICENSE")
        if os.path.isfile(icu_lic):
            shutil.copy2(icu_lic, os.path.join(icu_src, "LICENSE"))
        shutil.rmtree(tmp_clone, ignore_errors=True)
    # NOTE: do NOT apply the macOS pkgdata %s-split fix here — on linux the
    # original "…%s%s…" template correctly produces "-Wl,-soname -Wl,libX.so".
    return icu_src


if IS_LINUX:
    icu_out = os.path.join(icu_root, PLAT, "build")
    if not os.path.isfile(os.path.join(icu_out, "libicuuc.so.74")):
        print(f"== Building ICU 74.2 shared ({PLAT}) ==")
        # build_tools ships a prebuilt x86_64 python that icu's configure may pick
        # up via PATH injection — remove it so the system python is used instead
        bundled_py = os.path.join(BT, "tools", "linux", "python3")
        if os.path.isdir(bundled_py):
            shutil.rmtree(bundled_py, ignore_errors=True)
        icu_src = icu_src_dir()
        build_dir = os.path.join(icu_root, PLAT + "_work")
        install_dir = os.path.join(icu_root, PLAT + "_install")
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(install_dir, ignore_errors=True)
        os.makedirs(build_dir, exist_ok=True)
        env = dict(os.environ, CFLAGS="-fPIC", CXXFLAGS="-fPIC", CC="gcc", CXX="g++")
        run([os.path.join(icu_src, "source", "runConfigureICU"), "Linux",
             f"--prefix={install_dir}"], cwd=build_dir, env=env)
        # -static-libstdc++/-static-libgcc like upstream
        icudefs = os.path.join(icu_src, "source", "icudefs.mk.in")
        txt = open(icudefs, encoding="utf-8").read()
        patched = txt.replace("LDFLAGS = @LDFLAGS@ $(RPATHLDFLAGS)",
                              "LDFLAGS = @LDFLAGS@ $(RPATHLDFLAGS) -static-libstdc++ -static-libgcc")
        if patched != txt:
            open(icudefs, "w", encoding="utf-8").write(patched)
        run(["make", "-j4"], cwd=build_dir, env=env)
        run(["make", "install"], cwd=build_dir, env=env)
        os.makedirs(icu_out, exist_ok=True)
        for lib in ["libicudata", "libicui18n", "libicuuc"]:
            src = os.path.join(install_dir, "lib", lib + ".so.74.2")
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(icu_out, lib + ".so.74"))
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(install_dir, ignore_errors=True)
        shutil.rmtree(icu_src, ignore_errors=True)
elif IS_WIN:
    icu_out = os.path.join(icu_root, PLAT, "build")
    if not os.path.isfile(os.path.join(icu_out, "icuuc.lib")):
        print("== Building ICU 74.2 (win_64, MSBuild) ==")
        icu_src_dir()
        os.chdir(BT)
        import icu
        icu.make()

# ---------------------------------------------------------------------------
# 5. Boost 1.72 static libs (cached)
# ---------------------------------------------------------------------------
if IS_WIN:
    boost_probe = os.path.join(CORE, "Common", "3dParty", "boost", "build", PLAT)
else:
    boost_probe = os.path.join(CORE, "Common", "3dParty", "boost", "build", PLAT, "lib", "libboost_regex.a")
if not os.path.exists(boost_probe) or (IS_WIN and not glob.glob(os.path.join(boost_probe, "**", "libboost_regex*.lib"), recursive=True)):
    print(f"== Building Boost 1.72 ({PLAT}) ==")
    os.chdir(BT)
    boost.make()
    shutil.rmtree(os.path.join(CORE, "Common", "3dParty", "boost", "boost_1_72_0"), ignore_errors=True)

# ---------------------------------------------------------------------------
# 6. hunspell headers
# ---------------------------------------------------------------------------
hunspell_hdr = os.path.join(CORE, "Common", "3dParty", "hunspell", "hunspell", "src", "hunspell", "hunspell.h")
if not os.path.isfile(hunspell_hdr):
    print("== Preparing hunspell headers ==")
    os.chdir(BT)
    hunspell.make(False)

# ---------------------------------------------------------------------------
# 7. CryptoPPLib & CompoundFileLib (cached)
# ---------------------------------------------------------------------------
os.chdir(BT)
if IS_WIN:
    crypto_probe = os.path.join(LIB_PLAT, "CryptoPPLib.lib")
    cfc_probe = os.path.join(LIB_PLAT, "CompoundFileLib.lib")
else:
    crypto_probe = os.path.join(LIB_PLAT, "libCryptoPPLib.a")
    cfc_probe = os.path.join(LIB_PLAT, "libCompoundFileLib.a")
if not os.path.isfile(crypto_probe):
    print("== Building CryptoPPLib ==")
    qmake.make(PLAT, os.path.join(CORE, "Common", "3dParty", "cryptopp", "project", "cryptopp.pro"))
if not os.path.isfile(cfc_probe):
    print("== Building CompoundFileLib ==")
    qmake.make(PLAT, os.path.join(CORE, "Common", "cfcpp", "cfcpp.pro"))

# ---------------------------------------------------------------------------
# 8. Build patched libraries + executable
# ---------------------------------------------------------------------------
print("== Building ascdocumentscore ==")
qmake.make(PLAT, os.path.join(SDK, "ChromiumBasedEditors", "lib", "ascdocumentscore.pro"))

print("== Building qtascdocumentscore ==")
qmake.make(PLAT, os.path.join(SDK, "ChromiumBasedEditors", "lib", "qt_wrapper", "qtascdocumentscore.pro"))

editor_pro = os.path.join(APPS, "win-linux", "ASCDocumentEditor.pro")
if not os.path.isfile(editor_pro):
    cands = glob.glob(os.path.join(APPS, "win-linux", "*.pro"))
    editor_pro = cands[0] if cands else editor_pro
print(f"== Building DesktopEditors ({os.path.basename(editor_pro)}) ==")
qmake.make(PLAT, editor_pro)

built = glob.glob(os.path.join(LIB_PLAT, "*ascdocumentscore*"))
if not built:
    raise RuntimeError(f"ascdocumentscore artifacts missing in {LIB_PLAT}")
print("DESKTOP OVERLAY BUILD OK:", ", ".join(os.path.basename(b) for b in built))
