#!/bin/bash
# Task 1.1: make the bot start by itself whenever the Mac turns on,
# and restart it if it ever crashes.
#
# It replaces the old test page (task 0.2): both use port 8000, and the bot
# still shows the same test page at https://hello.pashutbook.com
#
# Run from the project folder:   bash deploy/mac/install-bot-service.sh
# Run it again after every code update, to restart the bot with the new code.
# It asks for your Mac password once.

set -euo pipefail

LABEL="com.pashutbook.bot"
OLD_LABEL="com.pashutbook.hello"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$(command -v python3 || true)"
USER_NAME="$(whoami)"
LOG_DIR="$HOME/Library/Logs/pashut-book"
PLIST="/Library/LaunchDaemons/$LABEL.plist"
OLD_PLIST="/Library/LaunchDaemons/$OLD_LABEL.plist"

if [[ -z "$PYTHON" ]]; then
  echo "❌ python3 not found. Run: brew install python"
  exit 1
fi

case "$PROJECT_DIR" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Downloads"*)
    echo "❌ The project is in Documents, Desktop or Downloads."
    echo "   macOS blocks background programs from those folders."
    echo "   Move it to your home folder (~/pashut-book) and run this again."
    exit 1 ;;
esac

# Check the settings before installing, so a mistake shows up here and not
# hidden in the log.
for NAME in WHATSAPP_PHONE_NUMBER_ID WHATSAPP_ACCESS_TOKEN WHATSAPP_APP_SECRET WHATSAPP_VERIFY_TOKEN; do
  if ! grep -Eq "^${NAME}=.+" "$PROJECT_DIR/.env" 2>/dev/null; then
    echo "❌ $NAME is missing or empty in $PROJECT_DIR/.env (see the guide, Steps 1–4)."
    exit 1
  fi
done

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
    <string>$PROJECT_DIR/server/bot.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/bot.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/bot.log</string>
</dict>
</plist>
PLIST_END

echo "Installing the bot as a startup program (macOS will ask for your password)..."
# Stop and remove the old test page from task 0.2 (it used the same port).
if [[ -f "$OLD_PLIST" ]]; then
  sudo launchctl bootout system "$OLD_PLIST" 2>/dev/null || true
  sudo rm -f "$OLD_PLIST"
  echo "   Removed the old test page service."
fi
sudo launchctl bootout system "$PLIST" 2>/dev/null || true
sleep 1
sudo cp "$TMP" "$PLIST"
sudo chown root:wheel "$PLIST"
sudo chmod 644 "$PLIST"
rm "$TMP"
sudo launchctl bootstrap system "$PLIST"

sleep 2
if curl -fsS http://localhost:8000/health >/dev/null; then
  echo "✅ Done. The bot is running."
  echo "   To watch it live:  tail -f $LOG_DIR/bot.log   (Control + C to stop watching)"
else
  echo "⚠️  Installed, but the bot isn't answering yet. Wait 10 seconds and run:"
  echo "   curl http://localhost:8000/health"
  echo "   If it still fails, look at the last lines of the log:"
  echo "   tail -20 $LOG_DIR/bot.log"
fi
