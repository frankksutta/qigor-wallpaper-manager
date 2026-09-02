# Obsolete — the PyInstaller EXE build

Everything in this folder is kept for reference only. **Do not build or ship from
it.** The current build tool is `build.pyw` in the project root, which produces
`QiGor_Wallpaper_Manager_Setup.zip`.

## What is here

| File | What it was |
|---|---|
| `obsolete_build.pyw` | Snapshot of the build tool as of 2026-09-01, taken just before the 🔨 Build EXE path was removed. Still contains the full PyInstaller invocation, the `VSVersionInfo` writer, and the `--onefile --windowed` command line. |
| `obsolete_QiGor_Wallpaper_Manager.exe` | The last frozen single-file build, produced 2026-07-10 (31 MB). |

## Why it was retired

The single-file EXE is blocked by **Smart App Control** on Windows 11, and there
is no way to fix that from inside the build.

Smart App Control is WDAC-based. It gates **PE images at load** — `.exe`, `.dll`,
`.sys`, `.msi` — and allows one only if it is signed by a publisher Windows
already trusts, or if Microsoft's Intelligent Security Graph returns a positive
reputation verdict for that exact file hash. An unsigned build has neither.

We hit this for real. `QiGor_Wallpaper_Manager.exe` ran fine for three weeks and
then, on 2026-07-31, started being blocked:

- 168 block events in `Microsoft-Windows-CodeIntegrity/Operational`, event id **3077**
- from 2026-07-31 06:38:53 to 2026-08-01 09:18:54, then it stopped on its own
  while Smart App Control stayed in enforcement mode
- every 10-minute slideshow task fired and died with `0x800711C7`
  ("An Application Control policy has blocked this file")
- the toast named `svchost.exe`, never the blocked file, so it was useless for
  diagnosis

Nothing about the binary changed during that window. The verdict is a cloud
decision keyed to the file hash, so it is **non-deterministic and it resets on
every rebuild**. Any fresh unsigned release can be dead on arrival — for us and
for every recipient who has Smart App Control on — and unlike SmartScreen, Smart
App Control gives the user no "run anyway" override.

Smart App Control also cannot be re-enabled once turned off without reinstalling
Windows, so "just switch it off" is not a reversible workaround to suggest to
anyone.

## Why not just sign it

Considered and rejected on cost grounds, 2026-08-01. Azure Artifact Signing
(formerly Trusted Signing) is the only affordable trusted-root option at
$9.99/month, but its terms exclude free, trial, and sponsored subscriptions — and
the Microsoft nonprofit grant arrives as Azure Sponsorship credits, so the grant
cannot pay for it. It would need a separate pay-as-you-go subscription on the
society's own card, roughly $120/year. Artifact Signing issues no EV certificates
either, so reputation would still accrue per file hash rather than clearing
immediately.

## Why not a small C++ launcher instead

Rejected 2026-09-01. A compiled stub does not dodge Smart App Control — it *is* a
PE image, which is exactly what gets gated. The language that produced it is
irrelevant; only the signature and the reputation verdict matter, and a
newly-compiled unsigned binary has neither. It would land in precisely the same
place as the PyInstaller EXE.

It is also actively worse than the EXE it replaces: a small unsigned binary that
downloads a payload and executes it is the textbook shape of a downloader
trojan, and that is the most heavily penalised pattern in both ISG reputation and
antivirus heuristics.

## What replaced it

Ship no unsigned PE images at all.

The release is a zip containing the official python.org **embeddable CPython**
distribution plus plain `.py` source. Every executable image in the payload —
`pythonw.exe`, `python313.dll`, the Tcl/Tk DLLs — is already signed by the Python
Software Foundation, so Smart App Control has nothing to gate. It was verified on
an enforcing machine that unsigned third-party `.pyd` extensions (Pillow,
tkinterdnd2) import fine, because Smart App Control checks the process image at
launch and not the extension modules loaded afterwards.

Installation, shortcut creation, and updating are all done in Python, run by that
signed interpreter. The launchers are `.cmd` files, which are interpreted by a
Microsoft-signed `cmd.exe` and are not gated. PowerShell was deliberately avoided
for the same job: under Smart App Control it drops into Constrained Language
Mode, which breaks `New-Object -ComObject`, so shortcuts are created through
`IShellLinkW` via `ctypes` instead.

See `installer/` and `build.pyw` in the project root.

## Safe to delete

Yes, whenever the reference value runs out. Nothing in the build depends on this
folder. `obsolete_QiGor_Wallpaper_Manager.exe` is 31 MB and matches `*.exe` in
`.gitignore`, so it was never committed and exists only on this machine.

The stale `QiGor_Wallpaper_Manager_Portable.zip` left in the project root is the
direct ancestor of the new installer zip — same embeddable-CPython approach, no
install step — and is likewise safe to delete once a Setup zip has been built.
