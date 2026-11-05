<!-- SHARED MEMORY STORE -- both Claude accounts (frankk@4nt.org, frank.per@4nt.org) read
     and write these same files. The real files live in this project at .claude/memory/ ;
     each account reaches them through a directory junction at
     %USERPROFILE%\.claude-teamN\projects\<slug>\memory . OneDrive syncs them between
     machines. NEVER delete/recurse the junction path -- that destroys the real store.
     Set up 2026-08-14; full recipe is in the debabel store: shared-memory-across-accounts.md -->
- [Open work: the manager](qigor-open-work.md) — all pushed; 0.8.4 live, 0.8.5 (reminder fix) needs build + upload; recursive slideshow folders, and a dead playlist to raise.
- [Open work: the sync tool](qigor-sync-open-work.md) — handoff for 2026-09-04: the restyled tabs, the recycle bin, and the three hazards before touching it.
- [Heredocs mangle backslashes](bash-heredoc-mangles-backslashes.md) — patch scripts go in a Write-ed file; a heredoc silently corrupts `\n` and the patch quietly does nothing.
- [Scheduler's one-minute floor](task-scheduler-minute-floor.md) — schtasks rejects PT5S/PT30S, which is why slideshow preview is a Tk timer.
- [Drive latency + the emoji font load](drive-listing-costs-half-a-second.md) — the two reasons an app is slow to start: ~0.5s per Drive folder listing, ~0.9s for the first emoji in the process.
- [Startup cost is emoji](tk-startup-cost-emoji.md) — 716ms for the first emoji glyph in Tk; never query schtasks on the main thread.
- [GUI overhaul verified](gui-overhaul-untested-handoff.md) — every tab driven button-by-button at 0.8.3; how to script a modal Tk GUI without deadlocking.
- [Installer release state](installer-release-state.md) — v0.8.4 published, 0.8.5 next; version.json must ship with every release or updates never fire.
- [Portable over signing](portable-distribution-decision.md) — why QiGor ships embeddable Python + plain source instead of a signed exe, an obfuscated build, or a C++ stub.
- [Smart App Control constraint](smart-app-control-constraint.md) — SAC enforces on this machine and blocks unsigned builds unpredictably, per file hash.
- [License still undecided](repo-public-license-pending.md) — public repo, no LICENSE or README; frank picks the license, don't choose for him.
