#!/usr/bin/env bash

set -Eeuo pipefail
LATEST_FILE="https://raw.githubusercontent.com/T3chieJack/FlipperPlayer/main/latest.txt"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/FlipperPlayer"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/FlipperPlayer.XXXXXXXX")"
ZIP="$STAGE/FlipperPlayer.zip"
EXTRACT="$STAGE/extracted"

cleanup() { rm -rf -- "$STAGE"; }
fail() { printf 'Installation failed: %s\n' "$*" >&2; exit 1; }
command_path() { command -v "$1" 2>/dev/null || true; }
desktop_quote() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//\`/\\\`}
    value=${value//\$/\\\$}
    printf '"%s"' "$value"
}

trap cleanup EXIT
trap 'fail "an error occurred on line $LINENO."' ERR
printf '\033[36mInstalling FlipperPlayer...\033[0m\n'

CURL="$(command_path curl)"
[[ -n "$CURL" ]] || fail "curl is required. Install it with your distribution's package manager."
PYTHON="$(command_path python3)"
[[ -n "$PYTHON" ]] || fail "Python 3.11 or newer is required."
"$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' ||
    fail "Python 3.11 or newer is required."

mkdir -p -- "$EXTRACT"
DOWNLOAD_URL="$("$CURL" --location --fail --silent --show-error "$LATEST_FILE")"
DOWNLOAD_URL="${DOWNLOAD_URL//$'\r'/}"
DOWNLOAD_URL="${DOWNLOAD_URL//$'\n'/}"
[[ "$DOWNLOAD_URL" == https://* ]] || fail "latest.txt did not contain a valid HTTPS URL."
"$CURL" --location --fail --show-error "$DOWNLOAD_URL" --output "$ZIP" ||
    fail "Download failed."

"$PYTHON" - "$ZIP" "$EXTRACT" <<'PY'
import sys
import zipfile

archive, destination = sys.argv[1:]
with zipfile.ZipFile(archive) as source:
    source.extractall(destination)
PY

PLAYER="$(find "$EXTRACT" -type f -name player.py -print -quit)"
[[ -n "$PLAYER" ]] || fail "player.py was not found in the ZIP."
PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p -- "$INSTALL_DIR"
cp -a -- "$PLAYER_DIR/." "$INSTALL_DIR/"

printf 'Installing Python packages...\n'
rm -rf -- "$INSTALL_DIR/.venv"
"$PYTHON" -m venv "$INSTALL_DIR/.venv" ||
    fail "Could not create a virtual environment. Install your distribution's python3-venv package."
"$INSTALL_DIR/.venv/bin/python" -m pip install "pygame>=2.6,<3" "Pillow>=12,<13" ||
    fail "Python package installation failed."

[[ -f "$INSTALL_DIR/player.py" ]] || fail "The installed player.py could not be found."
ICON_PATH=""
for candidate in "$INSTALL_DIR/Assets/logo.png" "$INSTALL_DIR/Assets/logo.svg" "$INSTALL_DIR/Assets/logo.ico"; do
    if [[ -f "$candidate" ]]; then ICON_PATH=$candidate; break; fi
done

LAUNCHER="$INSTALL_DIR/FlipperPlayer"
printf '%s\n' '#!/usr/bin/env bash' 'cd -- "$(dirname -- "$0")"' \
    'exec ./.venv/bin/python ./player.py "$@"' > "$LAUNCHER"
chmod +x -- "$LAUNCHER"

mkdir -p -- "$APPLICATIONS_DIR"
APPLICATION_FILE="$APPLICATIONS_DIR/flipperplayer.desktop"
{
    printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=FlipperPlayer' 'Comment=FlipperPlayer'
    printf 'Exec=%s\n' "$(desktop_quote "$LAUNCHER")"
    printf 'Path=%s\n' "$INSTALL_DIR"
    [[ -z "$ICON_PATH" ]] || printf 'Icon=%s\n' "$ICON_PATH"
    printf '%s\n' 'Terminal=false' 'Categories=AudioVideo;Player;'
} > "$APPLICATION_FILE"
chmod +x -- "$APPLICATION_FILE"

DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
elif [[ -d "$HOME/Desktop" ]]; then
    DESKTOP_DIR="$HOME/Desktop"
fi
if [[ -n "$DESKTOP_DIR" && -d "$DESKTOP_DIR" ]]; then
    cp -- "$APPLICATION_FILE" "$DESKTOP_DIR/FlipperPlayer.desktop"
    chmod +x -- "$DESKTOP_DIR/FlipperPlayer.desktop"
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

trap - ERR
printf '\n\033[32mFlipperPlayer installed successfully.\033[0m\n'
printf 'It is available in your application menu'
if [[ -n "$DESKTOP_DIR" && -d "$DESKTOP_DIR" ]]; then printf ' and on your Desktop'; fi
printf '.\n'
