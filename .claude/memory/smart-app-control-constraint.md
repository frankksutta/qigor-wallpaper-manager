---
name: smart-app-control-constraint
description: "Smart App Control is enforcing on frank's dev machine and blocks unsigned QiGor exe builds unpredictably, per file hash — the constraint that shaped the distribution choice."
metadata: 
  node_type: memory
  type: project
  originSessionId: 81d39a3a-eefb-404c-a939-36d2369a642c
  modified: 2026-08-02T10:46:36.684Z
---

Smart App Control is **on and enforcing** on this development machine
(`HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState = 1`).
It cannot be turned back on once disabled without reinstalling Windows, so
switching it off is not a reversible experiment.

Observed on the unsigned PyInstaller build (`QiGor_Wallpaper_Manager.exe`, built
2026-07-10, which had worked fine for three weeks):

- 168 block events, `Microsoft-Windows-CodeIntegrity/Operational` id **3077**
- began 2026-07-31 06:38:53, ended 2026-08-01 09:18:54 — then stopped by itself
  while SAC remained in enforcement mode
- during the window every 10-minute slideshow task fired and died with
  `0x800711C7` — "An Application Control policy has blocked this file"
- the notification names the *launcher*, `svchost.exe` → "Host Process for
  Windows", never the blocked file, which makes the toast useless for diagnosis

The lesson that drove the design: SAC's verdict is a **cloud reputation decision
keyed to the file hash**, so it is non-deterministic and resets for every new
build. Any fresh unsigned release can be dead on arrival for a day or more, for
frank and for every recipient with SAC enabled — and unlike SmartScreen, SAC
gives the user no "run anyway" override.

Useful diagnostic commands: filter that log for id 3076 (audit) and 3077 (block);
`net helpmsg` on the decimal low word of a task's `LastTaskResult`; and
`Get-MpPreference` to rule out Controlled Folder Access and ASR rules first, both
of which were off here.

Worked around by [[portable-distribution-decision]].
