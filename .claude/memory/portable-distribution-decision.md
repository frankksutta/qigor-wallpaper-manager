---
name: portable-distribution-decision
description: Why QiGor ships as a portable embeddable-Python zip with plain source rather than a signed exe or an obfuscated build.
metadata: 
  node_type: memory
  type: project
  originSessionId: 81d39a3a-eefb-404c-a939-36d2369a642c
  modified: 2026-09-01T19:23:26.870Z
---

Decided 2026-08-01: distribute via a portable zip (official embeddable CPython +
plain `.py` source) instead of buying a code-signing certificate.

**Why not sign.** Azure Artifact Signing (formerly Trusted Signing) is the only
affordable Trusted-Root option at $9.99/month, but its FAQ explicitly refuses
"free, trial, or sponsored" Azure subscriptions — and the Microsoft nonprofit
$2,000/year grant is delivered as Azure Sponsorship credits. So the grant cannot
pay for it; it would need a separate pay-as-you-go subscription billed to a card,
about $120/year of the society's own money. Artifact Signing also issues no EV
certificates, so SmartScreen reputation would still accrue per file hash rather
than clearing immediately.

**Why not obfuscate.** `.pyc` was considered and rejected: AI-assisted
decompilation recovers near-original source in minutes, so it is decorative. And
anything genuinely compiled (Nuitka, Cython, PyArmor) emits executable images,
which is exactly what Smart App Control gates — so real protection loops straight
back to needing a signature. The design worth protecting is visible from running
the app anyway.

**Why the portable route works.** Smart App Control gates the process image at
launch, not extensions loaded afterwards. Verified empirically on this machine
that unsigned Pillow `.pyd` files import fine under enforcing SAC. So a
PSF-signed `pythonw.exe` plus unsigned third-party wheels is deterministically
allowed, with no cloud reputation verdict in the loop.

**Why not a C++ launcher stub.** Raised and rejected 2026-09-01. A compiled stub
does not dodge Smart App Control — it *is* a PE image, which is precisely what
gets gated. Language is irrelevant; only the signature and the ISG reputation
verdict matter, and a newly compiled unsigned binary has neither, so it lands in
exactly the same place as the PyInstaller EXE. It is also worse than what it
replaces: a small unsigned binary that downloads a payload and executes it is
the textbook downloader-trojan shape, the most heavily penalised pattern in both
ISG reputation and AV heuristics. The rule that came out of it and now governs
the build: **ship zero unsigned PE images**, and let signed interpreters
(`pythonw.exe`) and signed shells (`cmd.exe` running plain `.cmd`) do all the
executing. PowerShell is avoided for the same reason it looks tempting — under
Smart App Control it drops to Constrained Language Mode, which breaks
`New-Object -ComObject`, so shortcuts go through `IShellLinkW` via `ctypes`.

Licensing, not obfuscation, is the actual lever here — see
[[repo-public-license-pending]]. Implementation state in
[[installer-release-state]]; the mechanism it dodges is in
[[smart-app-control-constraint]].
