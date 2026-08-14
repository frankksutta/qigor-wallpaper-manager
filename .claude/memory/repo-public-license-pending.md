---
name: repo-public-license-pending
description: "qigor-wallpaper-manager is a public GitHub repo with no LICENSE or README; frank has not yet chosen a license, and that decision is his to make."
metadata: 
  node_type: memory
  type: project
  originSessionId: 81d39a3a-eefb-404c-a939-36d2369a642c
  modified: 2026-08-02T10:46:44.621Z
---

`github.com/frankksutta/qigor-wallpaper-manager` is **public** (`build.pyw` creates
it with `"private": False`) and all 18 `.py`/`.pyw` files are tracked and pushed.
There is no `LICENSE` and no `README.md`.

This matters because it is the real exposure. Frank raised wanting to keep the
source private; hiding the shipped code is moot while the repo publishes it. A
public repo with no license reads to most people as "help yourself," even though
default copyright is technically all-rights-reserved.

**Open decision, deliberately left to frank** as of 2026-08-01 — do not pick one
unprompted:
- GPL-3.0 — derivatives stay open and must attribute
- MIT / Apache-2.0 — attribution only; Apache adds a patent grant
- keep it genuinely restricted — then the repo should go private, or split into a
  private source repo plus a public release-only repo

Noted at the time: given the project belongs to a Buddhist preservation society,
open-with-a-license may serve the mission better than restriction — but that is
frank's call, not a technical constraint. Writing `LICENSE` + `README.md` was
offered and is still pending his choice.

Context in [[portable-distribution-decision]].
