FLY LIKE IRON MAN  -  a No Man's Sky mod by DooDooDevan
=======================================================
Version 1.0.1 for No Man's Sky build 185034 (Windows, Steam)

Free flight where you look, flames from both hands and both feet, an Iron Man
pose that leans with your speed, an afterburner, sonic booms, an interplanetary
cruise, and flying straight into space, into space stations and the Space
Anomaly, and under water.


NEEDS
-----
- Windows 10 or 11, 64-bit.
- No Man's Sky on Steam, build 185034 (the launcher checks it). Other stores
  (GOG, Xbox / Game Pass) are not supported.
- The game's display mode set to Borderless or Windowed (Options > Display):
  the HUD is drawn over the game and can't show over exclusive Fullscreen.
- Nothing to install: Python and everything else ship in the "runtime" folder.


INSTALL AND START
-----------------
1. Unzip the whole download into a folder you can write to (for example
   C:\Games\FlyLikeIronMan). Not into Program Files or the game's own folder.
2. Start Steam. Close No Man's Sky.
3. Double-click "Start Fly Like Iron Man.bat". It finds the game, checks its
   version, copies its game files into No Man's Sky\GAMEDATA\MODS, and starts
   the game. Windows may say "Windows protected your PC": More info > Run anyway.
   Leave the extra windows open while you play (closing them closes the game).
4. Press a key at the game's "Mod Warning" screen and load your save.
5. If the launcher asks for it, stand still outside on open ground until it
   says "Ready" (your character jumps once).
6. Double-tap Space (or press F8) to fly.
Next time: just double-click "Start Fly Like Iron Man.bat" again.


KEYBOARD AND MOUSE (change any key in Suit Control, F7)
------------------
  Double-tap Space / F8 ... fly on / off
  Mouse ................... you fly where you look
  W / S ................... throttle up / down (it stays where you leave it);
                            at a hover, hold S to back up; double-tap S to brake
  A / D ................... sidestep at a hover; roll while flying forward
  R / F ................... up / down
  Shift ................... afterburner
  Caps Lock ............... sonic boom (each press one blast); in space: press
                            for the interplanetary cruise, hold for more speed
  F7 ...................... Suit Control (settings, sounds, keys, repairs)
  Hold End (1 s) .......... power the suit down


CONTROLLER (Xbox / XInput)
----------
  Double-tap A ............ fly on / off
  Left stick .............. throttle; at a hover it also moves you sideways
  Right stick ............. camera: you fly where you look
  B / X (hold) ............ up / down
  LB / RB (hold) .......... roll left / right while flying forward; sideways
                            at a hover
  Left stick up twice ..... afterburner (flick it up, back, up)
  Left stick back twice ... hard brake
  Right stick click ....... sonic boom; in space: the interplanetary cruise
  Both stick clicks (hold)  power the suit down
  While you fly the game ignores its own jobs on these buttons; on foot they
  are the game's again.


SPACE, STATIONS, THE ANOMALY, WATER
-----------------------------------
- Fly straight up into space and aim at a planet to come back down.
- Fly into a space station's mouth or the Space Anomaly's tunnel: it pulls you
  in to the landing pads, no ship needed. Fly back toward the exit to leave.
- In Iron Man mode the quick menu (X) has Summon the Space Anomaly and the
  Galaxy Map.
- Under water you keep flying, with the same poses.


SETTINGS
--------
Suit Control (F7 in the game, or "Suit Control.bat") changes everything and
saves it at once. Your settings are in settings.ini in this folder; delete it
to get the defaults back.


UNINSTALL
---------
1. Close No Man's Sky.
2. Double-click "Uninstall Fly Like Iron Man.bat" (removes the mod's files from
   No Man's Sky\GAMEDATA\MODS).
3. Delete this folder. Nothing was installed anywhere else.


PROBLEMS
--------
- Double-click "Troubleshoot.bat": it checks the game folder, version and files,
  and writes app\report.txt (your user name and PC name blanked out) to attach
  to a bug report.
- No flames or poses: start the game with the launcher (close it first).
- After a No Man's Sky update the mod stops itself and the game starts normally
  until the mod is updated.
- The mod changes the game's memory while it runs, which some antivirus programs
  flag. It's open source: the code is on GitHub (DooDooDevan/FlyLikeIronMan).


LICENCE
-------
Free to use and share with credit to DooDooDevan; no selling (CC BY-NC 4.0, see
LICENSE.txt). The bundled software's licences are in LICENSES.
