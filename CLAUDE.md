# CLAUDE.md — Office board (modular LED panel)

Read this first every session, then `docs/plan.md`, which holds every decision made so far.

## Who you're working with

Joe owns this project. He doesn't write code: you do all the coding, and he makes the design calls.
- Explain changes in plain language. Lead with what changes on the panel or web page.
- Show visual changes before he has to imagine them: a preview image, or an animated GIF for scrolling.
- Ask before pushing to GitHub or creating anything there. Commit freely with clear messages.
- Don't change an agreed decision in `docs/plan.md` unless Joe asks. If one causes a problem, explain
  it and offer options. When Joe changes a decision, update the plan and note the date.

## What it is

Raspberry Pi 3A+ + 64x32 RGB LED panel, 3mm pitch, in Joe's office. Shows modules (clock/weather,
stocks, NYRA racing, MLB, NFL) that can each be turned on and off from a web UI at
`officeboard.local:8080`, and tests scrolling against static pages.

Built on the odds board, **itsposttime** (https://github.com/djjoman68/itsposttime; local copy in
`../itsposttime/itsposttime`), which is built on the plane tracker (c0wsaysmoo/plane-tracker-rgb-pi),
based on ColinWaddell/FlightTracker (GPL-3.0). Read itsposttime's CLAUDE.md before reusing its code:
its NYRA notes (page structure, race lifecycle, polling limits) apply here unchanged.

Repo: https://github.com/djjoman68/officeboard (public; not yet created on GitHub).

## Status

- Oct 22 2026: plan agreed (`docs/plan.md`). Repo folder created. No code yet. Next: build order step 1
  (foundation).
- Hardware: the P3 panel has not been tested yet.

## Working rules

- This folder is its own git repo, separate from the pick5 repo in the parent folder.
- Never commit `config/*.json` (secrets, Pi settings).
- License is GPL-3.0. Keep credits in README.md. When copying a file from itsposttime or the plane
  tracker, keep its notes at the top and add "Modified for the office board".
- Keep NYRA polling gentle: use itsposttime's limits, never faster.
- Data sources are free tiers or unofficial feeds: cache results, poll no faster than needed, and keep
  showing the last good data when a fetch fails.
- The Pi runs one copy only (lock file + systemd).
