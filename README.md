# FlipperPlayer

FlipperPlayer is a Windows/Linux desktop player for Flipper Zero animation frames.

## Install

Python 3.11 or newer is required. Download Python from [python.org](https://www.python.org/downloads/) and enable **Add Python to PATH** during installation.

# WINDOWS
Open Command Prompt and run:

```cmd
curl.exe -L "https://raw.githubusercontent.com/T3chieJack/FlipperPlayer/main/install.cmd" -o "%TEMP%\FlipperPlayer-install.cmd" && call "%TEMP%\FlipperPlayer-install.cmd"
```
# Linux
Open a Terminal and run:

```Terminal
curl.exe -L "https://raw.githubusercontent.com/T3chieJack/FlipperPlayer/main/install.cmd" -o "%TEMP%\FlipperPlayer-install.cmd" && call "%TEMP%\FlipperPlayer-install.cmd"
```

The installer:

- downloads the latest release;
- installs the required Python packages;
- installs FlipperPlayer under `%LOCALAPPDATA%\Programs\FlipperPlayer`;
- adds shortcuts to the Desktop and Start Menu.

To pin it to the taskbar, search for **FlipperPlayer** in the Start Menu, right-click it, and select **Pin to taskbar**.

## Use

- Click **Playing: {...}** to choose an animation.
- Scroll the animation list to see the rest.
- Toggle **Flipper UI** to show or hide the Flipper body.
- Drag the top bar to move the window.
- Use the controls in the top-right to minimise or close it.

Animation order and playback speed are read from each animation's `meta.txt` file.

## Portable use

Install the dependencies:

```cmd
py -3 -m pip install pygame Pillow
```

Then run:

```cmd
py -3 player.py
```

Keep `player.py`, `logo.png`, `Assets`, and `Animations` together in the same folder.

## Remove

1. Close FlipperPlayer.
2. Delete `%LOCALAPPDATA%\Programs\FlipperPlayer`.
3. Delete the FlipperPlayer shortcuts from the Desktop and Start Menu.
