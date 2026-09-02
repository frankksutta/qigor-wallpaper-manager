QiGor is now a proper installed app rather than a folder you keep somewhere.

- Installs to your user account, with a Start Menu entry, an optional desktop shortcut, and an Uninstall entry in Settings ▸ Apps. No administrator password.
- `QiGor-Setup.cmd` downloads, verifies and installs in one double-click, so there is no zip to unpack or keep track of. It checks the published version first and transfers about a kilobyte — not the whole installer — if you already have the latest build.
- Built-in updates: QiGor checks once a day, shows what changed, and verifies the download against a published checksum before replacing anything.
- Upgrading from an older copy takes over its slideshow and reminder schedules, keeping your intervals, and tells you where the old folder is.
- Uninstall from Settings ▸ Apps, from Help ▸ Uninstall inside the app, or with `winget uninstall`. It asks a running copy to close first, so it can never half-remove itself.
- Every install and uninstall is written to `%USERPROFILE%\.qigor-wallpaper\install_log.txt`, so a window that closes too fast is no longer the end of the story.
- No unsigned `.exe` anywhere, so Smart App Control has nothing to block. Everything that runs is signed by the Python Software Foundation or by Microsoft.
