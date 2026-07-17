#!/bin/sh
# Wrapper for launchd: extracts Claude env vars from shell rc files, fetches a
# GitHub token via `gh auth token`, then execs claude.

# Auto-detect shell config file (zsh -> bash -> bash_profile)
for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile"; do
    if [ -f "$rc" ]; then
        eval "$(grep -E '^export (ANTHROPIC_(AUTH_TOKEN|BASE_URL)|CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC)=' "$rc" | tail -3)"
        [ -n "$ANTHROPIC_AUTH_TOKEN" ] && break
    fi
done
export ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC

# Best-effort cleanup before each scheduled digest run.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SKILL_DIR="${AI_DAILY_DIGEST_DIR:-$SCRIPT_DIR}"
if [ -x "$SKILL_DIR/scripts/cleanup_expired.sh" ]; then
    "$SKILL_DIR/scripts/cleanup_expired.sh" >/dev/null 2>&1 || true
fi

# GitHub token for GitHub-backed sources. Without this, unauthenticated requests
# are limited to 60/hour and some categories may be sparse.
for gh_path in /opt/homebrew/bin/gh /usr/local/bin/gh /usr/bin/gh; do
    if [ -x "$gh_path" ]; then
        GITHUB_TOKEN="$($gh_path auth token 2>/dev/null)"
        [ -n "$GITHUB_TOKEN" ] && export GITHUB_TOKEN && break
    fi
done

# Auto-detect claude binary path.
for claude_path in /opt/homebrew/bin/claude /usr/local/bin/claude; do
    [ -x "$claude_path" ] && exec "$claude_path" "$@"
done

exec claude "$@"
