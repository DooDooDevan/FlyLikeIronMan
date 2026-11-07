# Fly Like Iron Man

A No Man's Sky mod by **DooDooDevan**: free flight where you look, flames from both hands and both feet, an Iron Man
pose that leans with your speed, an afterburner, sonic booms, an interplanetary cruise, and flying straight into
space, into space stations and the Space Anomaly, and under water.

Version 1.0.0, for No Man's Sky build 184271 (Windows, Steam).

## Download

Get **FlyLikeIronMan_1.0.0.zip** from [Releases](../../releases); the release notes give its SHA-256 so you can check
your download. GitHub's own "Source code" and "Download ZIP" archives hold the same files and work too.

## What's in this repository

Everything the mod needs, ready to run:

| Path | What it is |
|---|---|
| `app\*.py` | the mod itself: the flight script, the in-game half (`limbjets_core.py`, loaded by NMS.py), the HUD, Suit Control |
| `app\mods\limbjets_mod.py` | the NMS.py mod entry point |
| `app\sounds`, `app\data` | the mod's sounds and pose data |
| `GAMEDATA\MODS\FlyLikeIronMan` | the game-side files the launcher copies into No Man's Sky |
| `*.bat` | the launcher, Suit Control, troubleshooting and uninstall |
| `runtime\` | Python and the libraries the mod uses (below) |
| `LICENSES` | the licences of the bundled software |

`runtime\` is Python 3.13, the official embeddable package from python.org plus tkinter (for Suit Control), with the
libraries the mod uses (NMS.py, pyMHF, NumPy, Pillow, ...) as pip installed them. Tests, type stubs and other unused
parts are left out. The only edited files are `python313._pth` (where Python finds the libraries and the mod) and
NMS.py's `pymhf.toml` (its debug window switched off).

The mod changes the game's memory while it runs (that's how it flies), which some antivirus programs flag. Nothing
here goes online: it talks only to the game on your own PC.

## Needs

- Windows 10 or 11, 64-bit.
- No Man's Sky on Steam, build 184271 (the launcher checks it). Other stores are not supported.
- The game's display mode set to Borderless or Windowed (the HUD can't show over exclusive Fullscreen).

## Install and start

1. Unzip the download into a folder you can write to (not Program Files, not the game folder).
2. Start Steam. Close No Man's Sky.
3. Double-click `Start Fly Like Iron Man.bat`. It finds the game, checks its version, copies its game files into
   `No Man's Sky\GAMEDATA\MODS` and starts the game. Leave the extra windows open while you play.
4. Press a key at the game's "Mod Warning" screen and load your save.
5. Double-tap Space (or press F8) to fly.

## Controls

| Keyboard and mouse | | Controller | |
|---|---|---|---|
| Double-tap Space / F8 | fly on / off | Double-tap A | fly on / off |
| Mouse | fly where you look | Right stick | camera: fly where you look |
| W / S | throttle (it stays where you leave it); double-tap S to brake | Left stick | throttle; sideways at a hover |
| A / D | sidestep at a hover, roll flying forward | LB / RB | roll flying forward, sideways at a hover |
| R / F | up / down | B / X | up / down |
| Shift | afterburner | Left stick up twice | afterburner |
| Caps Lock | sonic boom; in space, the interplanetary cruise | Right stick click | sonic boom; in space, the cruise |
| F7 | Suit Control (settings, sounds, keys) | Left stick back twice | hard brake |
| Hold End | power the suit down | Both stick clicks (hold) | power the suit down |

## Uninstall

Close the game, run `Uninstall Fly Like Iron Man.bat`, then delete the folder. Nothing is installed anywhere else.

## Licence

Free to use and share with credit to DooDooDevan; no selling (CC BY-NC 4.0, see `LICENSE.txt`). The bundled
software keeps its own licences (`LICENSES`, `CREDITS.txt`). No Man's Sky is © Hello Games; this mod is not made by
or affiliated with Hello Games, Marvel or Disney.
