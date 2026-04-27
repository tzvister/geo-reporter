#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# GEO Reporter — Exit dev mode
# ============================================================
#
# Removes the symlinks created by ./dev-link.sh and re-installs proper
# copies from the current branch's working tree. After this, the
# installed skill is a frozen snapshot — your subsequent edits to the
# repo no longer affect Claude Code until you re-run dev-link.sh or
# install.sh.
#
# Files not managed by this project (e.g. your local-only geo-observe
# skill) are left untouched.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SKILLS_DIR="${CLAUDE_DIR}/skills"
AGENTS_DIR="${CLAUDE_DIR}/agents"
INSTALL_DIR="${SKILLS_DIR}/geo"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_ok()   { echo -e "${GREEN}✓${NC} $1"; }
print_info() { echo -e "${BLUE}→${NC} $1"; }

if [ ! -f "${REPO_DIR}/geo/SKILL.md" ]; then
    echo "Run this from the geo-reporter repo root."
    exit 1
fi

echo ""
echo -e "${BLUE}→ Removing dev-mode symlinks...${NC}"
echo ""

unlink_if_link() {
    local target="$1"
    if [ -L "$target" ]; then
        rm "$target"
        print_ok "unlinked $(basename "$target")"
    fi
}

# Main /geo skill components
unlink_if_link "${INSTALL_DIR}/SKILL.md"
unlink_if_link "${INSTALL_DIR}/scripts"
unlink_if_link "${INSTALL_DIR}/schema"

# Sub-skills
for skill_dir in "${REPO_DIR}/skills"/*/; do
    if [ -d "$skill_dir" ]; then
        skill_name=$(basename "$skill_dir")
        unlink_if_link "${SKILLS_DIR}/${skill_name}"
    fi
done

# Agents
for agent_file in "${REPO_DIR}/agents/"*.md; do
    if [ -f "$agent_file" ]; then
        unlink_if_link "${AGENTS_DIR}/$(basename "$agent_file")"
    fi
done

echo ""
print_info "Re-installing proper copies via install.sh..."
echo ""

# Hand off to install.sh (which copies, doesn't symlink)
"${REPO_DIR}/install.sh" < /dev/null

echo ""
echo -e "${YELLOW}DEV MODE OFF — installed copy is now frozen at the current branch.${NC}"
echo ""
