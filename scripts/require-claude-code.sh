#!/usr/bin/env bash
# cfm runtime environment gate.
# Claude Code sets CLAUDECODE=1 in every spawned Bash process; no other
# surface (Cowork, Chat) does. This is the single gate script — referenced
# by every cfm skill (step 0), cfm:doctor (check #0), and guard.sh.
# Never duplicate this logic elsewhere.

if [ "$CLAUDECODE" != "1" ]; then
  echo "cfm runs only in Claude Code (terminal, IDE, or the Desktop Code tab)." >&2
  echo "Your project config and brief are untouched — open this repo in Claude Code to continue." >&2
  exit 1
fi
