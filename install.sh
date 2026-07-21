#!/bin/bash
# AI Daily Digest installer — sets up launchd for daily 09:07 runs

set -e

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_NAME="ai-daily-digest-launcher.sh"
LAUNCHER_PATH="$HOME/.local/bin/$LAUNCHER_NAME"
PLIST_NAME="com.user.ai-daily-digest.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
CLEANUP_PLIST_NAME="com.user.ai-daily-digest-cleanup.plist"
CLEANUP_PLIST_PATH="$HOME/Library/LaunchAgents/$CLEANUP_PLIST_NAME"
SKILLS_DIR="$HOME/.claude/skills"
SKILL_LINK="$SKILLS_DIR/ai-daily-digest"

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
chmod +x "$SKILL_DIR/scripts/cleanup_expired.sh"
echo "  ✓ $LAUNCHER_PATH"

# 3. Link into Claude Code skills directory
echo "Linking skill directory..."
mkdir -p "$SKILLS_DIR"
if [ -L "$SKILL_LINK" ] || [ -e "$SKILL_LINK" ]; then
    current_target="$(readlink "$SKILL_LINK" 2>/dev/null || true)"
    if [ "$current_target" != "$SKILL_DIR" ]; then
        echo "  ⚠️  $SKILL_LINK already exists; leaving it unchanged."
        echo "     Point it to this directory manually if Claude Code cannot find the skill:"
        echo "     $SKILL_DIR"
    else
        echo "  ✓ $SKILL_LINK"
    fi
else
    ln -s "$SKILL_DIR" "$SKILL_LINK"
    echo "  ✓ $SKILL_LINK -> $SKILL_DIR"
fi

# 4. Generate launchd plist
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
        <key>AI_DAILY_DIGEST_DIR</key>
        <string>$SKILL_DIR</string>
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

# 5. Generate cleanup launchd plist
echo "Generating cleanup plist..."
cat > "$CLEANUP_PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.ai-daily-digest-cleanup</string>

    <key>ProgramArguments</key>
    <array>
        <string>$SKILL_DIR/scripts/cleanup_expired.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>21</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/ai-daily-digest/cleanup-stdout.log</string>

    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/ai-daily-digest/cleanup-stderr.log</string>
</dict>
</plist>
EOF
echo "  ✓ $CLEANUP_PLIST_PATH"

# 6. Create .claude/settings.json for Agent auto-permission
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

# 7. Load launchd jobs
echo ""
echo "Loading launchd jobs..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl unload "$CLEANUP_PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
if launchctl load "$CLEANUP_PLIST_PATH" 2>/dev/null; then
    echo "  ✓ Loaded cleanup launchd job (21:00)"
else
    echo "  ⚠️  Cleanup launchd job did not load; trying crontab fallback..."
    cron_line="0 21 * * * $SKILL_DIR/scripts/cleanup_expired.sh"
    if command -v crontab >/dev/null 2>&1 && (
        crontab -l 2>/dev/null | grep -v 'ai-daily-digest/scripts/cleanup_expired.sh'
        echo "$cron_line"
    ) | crontab - 2>/dev/null; then
        echo "  ✓ Installed cleanup crontab fallback (21:00)"
    else
        echo "  ⚠️  Could not install a 21:00 cleanup scheduler."
        echo "     The digest launcher still runs cleanup before each 09:07 digest."
    fi
fi
echo "  ✓ Loaded digest job (09:07)"

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
echo "  launchctl unload $CLEANUP_PLIST_PATH"
echo "  crontab -l | grep -v 'ai-daily-digest/scripts/cleanup_expired.sh' | crontab -"
echo "  rm $PLIST_PATH $CLEANUP_PLIST_PATH $LAUNCHER_PATH"
echo "  rm $SKILL_LINK"
