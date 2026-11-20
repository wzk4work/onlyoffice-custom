#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

WORK_DIR = os.path.abspath(sys.argv[1])
OFFICIAL_APP = os.path.abspath(sys.argv[2])
QT_PARENT_DIR = os.path.abspath(sys.argv[3])

BT = os.path.join(WORK_DIR, "build_tools")
CORE = os.path.join(WORK_DIR, "core")
SDK = os.path.join(WORK_DIR, "desktop-sdk")

with open(os.path.join(BT, "config"), "w", encoding="utf-8") as f:
    f.write(
        "\n".join([
            'update="0"',
            'branch="master"',
            'clean="0"',
            'module="core desktop"',
            'develop="0"',
            'beta="0"',
            'platform="mac_64"',
            f'qt-dir="{QT_PARENT_DIR}"',
            'no-apps="0"',
            'multiprocess="1"',
            'sysroot="0"',
            "",
        ])
    )

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
base.set_env("BUILD_PLATFORM", "mac_64")
config.parse_defaults()
base.check_build_version(BT)
base.configure_common_apps()
ver = base.get_env("PRODUCT_VERSION") or "10.0.0"
config.extend_option("qmake_addon", f"URL_WEBAPPS_HELP=https://download.onlyoffice.com/install/desktop/editors/help/v{ver}/apps")

# 1. Stage prebuilt dynamic frameworks from the official DMG into core/build & cef/build
lib_mac64 = os.path.join(CORE, "build", "lib", "mac_64")
cef_mac64 = os.path.join(CORE, "Common", "3dParty", "cef", "mac_64", "build")
os.makedirs(lib_mac64, exist_ok=True)
os.makedirs(cef_mac64, exist_ok=True)

for fw in glob.glob(os.path.join(OFFICIAL_APP, "Contents", "Resources", "converter", "*.framework")):
    dst = os.path.join(lib_mac64, os.path.basename(fw))
    if not os.path.exists(dst):
        shutil.copytree(fw, dst, symlinks=True)

for fw_name in ["hunspell.framework", "ascdocumentscore.framework"]:
    fw_src = os.path.join(OFFICIAL_APP, "Contents", "Frameworks", fw_name)
    fw_dst = os.path.join(lib_mac64, fw_name)
    if not os.path.exists(fw_dst):
        shutil.copytree(fw_src, fw_dst, symlinks=True)

cef_fw = os.path.join(OFFICIAL_APP, "Contents", "Frameworks", "Chromium Embedded Framework.framework")
cef_dst = os.path.join(cef_mac64, "Chromium Embedded Framework.framework")
if not os.path.exists(cef_dst):
    shutil.copytree(cef_fw, cef_dst, symlinks=True)

# 2. Build x86_64 ICU 74.2 static libs (cached across CI runs)
icu_root = os.path.join(CORE, "Common", "3dParty", "icu")
icu_out = os.path.join(icu_root, "mac_64", "build")
if not os.path.isfile(os.path.join(icu_out, "libicuuc.a")):
    print("== Building ICU 74.2 (mac_64 only) ==")
    os.makedirs(icu_root, exist_ok=True)
    icu_src = os.path.join(icu_root, "icu")
    if not os.path.isdir(icu_src):
        tmp_clone = os.path.join(icu_root, "icu_tmp")
        shutil.rmtree(tmp_clone, ignore_errors=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", "release-74-2", "https://github.com/unicode-org/icu.git", tmp_clone], check=True)
        shutil.move(os.path.join(tmp_clone, "icu4c"), icu_src)
        icu_lic = os.path.join(tmp_clone, "LICENSE")
        if os.path.isfile(icu_lic):
            shutil.copy2(icu_lic, os.path.join(icu_src, "LICENSE"))
        shutil.rmtree(tmp_clone, ignore_errors=True)
    pkgdata = os.path.join(icu_src, "source", "tools", "pkgdata", "pkgdata.cpp")
    txt = open(pkgdata, encoding="utf-8").read()
    patched = txt.replace('cmd, "%s %s -o %s%s %s %s%s %s %s",', 'cmd, "%s %s -o %s%s %s %s %s %s %s",')
    if patched != txt:
        open(pkgdata, "w", encoding="utf-8").write(patched)
    sdk_path = base.find_mac_sdk()
    flags = f"-arch x86_64 -isysroot {sdk_path} -mmacosx-version-min=10.12"
    env = dict(os.environ, CFLAGS=flags, CXXFLAGS=flags + " --std=c++11", LDFLAGS=flags)
    build_dir = os.path.join(icu_root, "mac_64_work")
    install_dir = os.path.join(icu_root, "mac_64_install")
    shutil.rmtree(build_dir, ignore_errors=True)
    shutil.rmtree(install_dir, ignore_errors=True)
    os.makedirs(build_dir, exist_ok=True)
    subprocess.run([os.path.join(icu_src, "source", "runConfigureICU"), "MacOSX", f"--prefix={install_dir}", "--enable-static"], cwd=build_dir, env=env, check=True)
    subprocess.run(["make", "-j4"], cwd=build_dir, env=env, check=True)
    subprocess.run(["make", "install"], cwd=build_dir, env=env, check=True)
    os.makedirs(icu_out, exist_ok=True)
    shutil.copytree(os.path.join(install_dir, "include"), os.path.join(icu_out, "include"), dirs_exist_ok=True)
    for lib in ["libicudata.a", "libicui18n.a", "libicuuc.a"]:
        shutil.copy2(os.path.join(install_dir, "lib", lib), os.path.join(icu_out, lib))
    shutil.rmtree(build_dir, ignore_errors=True)
    shutil.rmtree(install_dir, ignore_errors=True)
    shutil.rmtree(icu_src, ignore_errors=True)

# 3. Build Boost 1.72 static libs (cached across CI runs)
boost_lib = os.path.join(CORE, "Common", "3dParty", "boost", "build", "mac_64", "lib", "libboost_regex.a")
if not os.path.isfile(boost_lib):
    print("== Building Boost 1.72 (mac_64) ==")
    os.chdir(BT)
    boost.make()
    shutil.rmtree(os.path.join(CORE, "Common", "3dParty", "boost", "boost_1_72_0"), ignore_errors=True)

# 4. Fetch hunspell sources (autogen/records.h is checked into core, so the
# real guard is the cloned hunspell repo itself)
hunspell_hdr = os.path.join(CORE, "Common", "3dParty", "hunspell", "hunspell", "src", "hunspell", "hunspell.h")
if not os.path.isfile(hunspell_hdr):
    print("== Preparing hunspell headers ==")
    os.chdir(BT)
    hunspell.make(False)

# 5. Build small static libs CryptoPPLib & CompoundFileLib (cached across CI runs)
os.chdir(BT)
if not os.path.isfile(os.path.join(lib_mac64, "libCryptoPPLib.a")):
    print("== Building CryptoPPLib ==")
    qmake.make("mac_64", os.path.join(CORE, "Common", "3dParty", "cryptopp", "project", "cryptopp.pro"))
if not os.path.isfile(os.path.join(lib_mac64, "libCompoundFileLib.a")):
    print("== Building CompoundFileLib ==")
    qmake.make("mac_64", os.path.join(CORE, "Common", "cfcpp", "cfcpp.pro"))

# 6. Build customized ascdocumentscore.framework
print("== Building ascdocumentscore.framework ==")
qmake.make("mac_64", os.path.join(SDK, "ChromiumBasedEditors", "lib", "ascdocumentscore.pro"))
built_bin = os.path.join(lib_mac64, "ascdocumentscore.framework", "Versions", "A", "ascdocumentscore")
if not os.path.isfile(built_bin):
    raise RuntimeError(f"Expected built binary missing: {built_bin}")
print("SDK OVERLAY BUILD OK:", built_bin)
