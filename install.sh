#!/bin/bash
# AI Daily Digest installer — sets up launchd for daily 09:07 runs

set -e

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_NAME="ai-daily-digest-launcher.sh"
LAUNCHER_PATH="$HOME/.local/bin/$LAUNCHER_NAME"
PLIST_NAME="com.user.ai-daily-digest.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "=== AI Daily Digest Installer ==="
echo ""

# 1. Check dependencies
echo "Checking dependencies..."

if ! command -v claude >/dev/null 2>&1; then
    echo "❌ Claude Code CLI not found. Install it first:"
    echo "   https://github.com/anthropics/claude-code"
    exit 1
fi
echo "  ✓ Claude Code CLI"

if ! command -v gh >/dev/null 2>&1; then
    echo "⚠️  GitHub CLI (gh) not found."
    echo "   Claude Code source will return 0 items without it (GitHub API limit 60/h)."
    echo ""
    read -p "   Install now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        brew install gh
        gh auth login
    else
        echo "   Skipping. You can install later: brew install gh && gh auth login"
    fi
else
    echo "  ✓ GitHub CLI"
    if ! gh auth status >/dev/null 2>&1; then
        echo "⚠️  GitHub CLI not logged in."
        read -p "   Login now? (y/n) " -n 1 -r
        echo
        [[ $REPLY =~ ^[Yy]$ ]] && gh auth login
    fi
fi

# Check for ANTHROPIC_AUTH_TOKEN
found_token=0
for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile"; do
    if [ -f "$rc" ] && grep -q "ANTHROPIC_AUTH_TOKEN" "$rc"; then
        found_token=1
        echo "  ✓ ANTHROPIC_AUTH_TOKEN found in $rc"
        break
    fi
done

if [ $found_token -eq 0 ]; then
    echo "⚠️  ANTHROPIC_AUTH_TOKEN not found in shell rc files."
    echo "   Add to ~/.zshrc (or ~/.bashrc):"
    echo '   export ANTHROPIC_AUTH_TOKEN="sk-..."'
    echo '   export ANTHROPIC_BASE_URL="https://api.anthropic.com"  # if using relay'
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
fi

echo ""

# 2. Copy launcher script
echo "Installing launcher script..."
mkdir -p "$HOME/.local/bin"
cp "$SKILL_DIR/ai-daily-digest-launcher.sh" "$LAUNCHER_PATH"
chmod +x "$LAUNCHER_PATH"
echo "  ✓ $LAUNCHER_PATH"

# 3. Generate launchd plist
echo "Generating launchd plist..."
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/Library/Logs/ai-daily-digest"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.ai-daily-digest</string>

    <key>ProgramArguments</key>
    <array>
        <string>$LAUNCHER_PATH</string>
        <string>-p</string>
        <string>AI 日报</string>
        <string>--dangerously-skip-permissions</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SKILL_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>7</integer>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/ai-daily-digest/stdout.log</string>

    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/ai-daily-digest/stderr.log</string>
</dict>
</plist>
EOF

echo "  ✓ $PLIST_PATH"

# 4. Create .claude/settings.json for Agent auto-permission
echo "Creating project-level permissions..."
mkdir -p "$SKILL_DIR/.claude"
cat > "$SKILL_DIR/.claude/settings.json" << 'EOF'
{
  "permissions": {
    "allowed": [
      {
        "type": "prompt",
        "tool": "Agent",
        "prompt": "*"
      }
    ]
  }
}
EOF
echo "  ✓ $SKILL_DIR/.claude/settings.json"

# 5. Load launchd job
echo ""
echo "Loading launchd job..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "  ✓ Loaded (next run: tomorrow 09:07)"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Test now:"
echo "  cd $SKILL_DIR"
echo "  claude -p 'AI 日报'"
echo ""
echo "View logs:"
echo "  tail -f ~/Library/Logs/ai-daily-digest/stdout.log"
echo ""
echo "Uninstall:"
echo "  launchctl unload $PLIST_PATH"
echo "  rm $PLIST_PATH $LAUNCHER_PATH"
