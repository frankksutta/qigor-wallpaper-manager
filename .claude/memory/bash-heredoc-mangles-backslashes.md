---
name: bash-heredoc-mangles-backslashes
description: "Backslash escapes inside a Bash heredoc arrive mangled in this harness, so multi-line Python edits go in a Write-ed patch file, never a heredoc."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6bdc9b61-d049-49ba-9611-50846bf90165
  modified: 2026-09-03T01:45:40.443Z
---

Self-observed, twice in the 2026-09-02 session, each time costing a failed
patch and a re-run.

A **quoted** heredoc (`python - <<'PYEOF'`) should pass its body through
literally. In this harness it does not: `"\\n"` written in the body arrives at
Python as `"\n"`, so a search string meant to match the two characters
backslash-n instead contains a real newline and never matches. The failure is
quiet — the patch script asserts, exits, and writes nothing, so the file looks
untouched and the next command reports success on stale code. That is how a
"cache is working" measurement was once read off a file that had never been
written.

**How to apply:** for any edit whose search or replacement text contains a
backslash — `"\n"` in a string literal, a Windows path, a regex — write the
patch script to the scratchpad with the Write tool and run it as a file.
Heredocs are fine only for backslash-free one-liners. Better still, have the
script `assert s.count(old) == 1` before writing, and `grep` the target
afterwards rather than trusting the exit code.

Related: the DPI/ImageGrab trap in [[gui-overhaul-untested-handoff]], which
failed the same way — a plausible-looking result from a measurement that was
wrong.
