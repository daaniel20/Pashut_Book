#!/bin/bash
# Task 0.2: make the test page start by itself whenever the Mac turns on,
# and restart it if it ever crashes.
#
# It creates a "LaunchDaemon": macOS's built-in way to run a program in the
# background from the moment the Mac starts, even before anyone logs in.
#
# Run from the project folder:   bash deploy/mac/install-hello-service.sh
# It asks for your Mac password once (needed to install a startup program).

set -euo pipefail

LABEL="com.pashutbook.hello"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$(command -v python3 || true)"
USER_NAME="$(whoami)"
LOG_DIR="$HOME/Library/Logs/pashut-book"
PLIST="/Library/LaunchDaemons/$LABEL.plist"

if [[ -z "$PYTHON" ]]; then
  echo "❌ python3 not found. Do Step 2 of the guide first (brew install python)."
  exit 1
fi

case "$PROJECT_DIR" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Downloads"*)
    echo "❌ The project is in Documents, Desktop or Downloads."
    echo "   macOS blocks background programs from those folders."
    echo "   Move it to your home folder (~/pashut-book) and run this again."
    exit 1 ;;
esac

mkdir -p "$LOG_DIR"
TMP="$(mktemp)"
cat > "$TMP" <<PLIST_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>UserName</key><string>$USER_NAME</string>
  <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$PROJECT_DIR/server/hello.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_DIR/hello.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/hello.log</string>
</dict>
</plist>
PLIST_END

echo "Installing the test page as a startup program (macOS will ask for your password)..."
sudo launchctl bootout system "$PLIST" 2>/dev/null || true
sudo cp "$TMP" "$PLIST"
sudo chown root:wheel "$PLIST"
sudo chmod 644 "$PLIST"
rm "$TMP"
sudo launchctl bootstrap system "$PLIST"

sleep 2
if curl -fsS http://localhost:8000/health >/dev/null; then
  echo "✅ Done. The test page is running at http://localhost:8000"
else
  echo "⚠️  Installed, but the page isn't answering yet. Wait 10 seconds and open"
  echo "   http://localhost:8000 in Safari. If it still fails, look at:"
  echo "   $LOG_DIR/hello.log"
fi
