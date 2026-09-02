<!-- SHARED MEMORY STORE -- both Claude accounts (frankk@4nt.org, frank.per@4nt.org) read
     and write these same files. The real files live in this project at .claude/memory/ ;
     each account reaches them through a directory junction at
     %USERPROFILE%\.claude-teamN\projects\<slug>\memory . OneDrive syncs them between
     machines. NEVER delete/recurse the junction path -- that destroys the real store.
     Set up 2026-08-14; full recipe is in the debabel store: shared-memory-across-accounts.md -->
- [Installer release state](installer-release-state.md) — v0.8.0 is installable and tested end to end, but nothing is uploaded yet; version.json must ship or updates never fire.
- [Portable over signing](portable-distribution-decision.md) — why QiGor ships embeddable Python + plain source instead of a signed exe, an obfuscated build, or a C++ stub.
- [Smart App Control constraint](smart-app-control-constraint.md) — SAC enforces on this machine and blocks unsigned builds unpredictably, per file hash.
- [License still undecided](repo-public-license-pending.md) — public repo, no LICENSE or README; frank picks the license, don't choose for him.
