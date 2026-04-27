#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# GEO Reporter — Dev mode (symlink local repo into ~/.claude)
# ============================================================
#
# Replaces the installed copies of every GEO Reporter skill, agent,
# and script with symlinks pointing back into THIS repo. After this,
# any edit you make in the repo (or any branch you check out) is
# immediately live in Claude Code with no install/copy step.
#
# Use case: testing a PR or iterating on a skill before merging.
#
# To revert (re-install proper copies from the current main):
#   ./dev-unlink.sh        (or just ./install.sh)
#
# Files NOT in the repo (e.g. your local-only `geo-observe` skill)
# are left untouched.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SKILLS_DIR="${CLAUDE_DIR}/skills"
AGENTS_DIR="${CLAUDE_DIR}/agents"
INSTALL_DIR="${SKILLS_DIR}/geo"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_ok()    { echo -e "${GREEN}✓${NC} $1"; }
print_info()  { echo -e "${BLUE}→${NC} $1"; }
print_warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
print_err()   { echo -e "${RED}✗${NC} $1"; }

# ----- Sanity checks -----
if [ ! -f "${REPO_DIR}/geo/SKILL.md" ]; then
    print_err "Run this from the geo-reporter repo root."
    exit 1
fi
mkdir -p "$SKILLS_DIR" "$AGENTS_DIR"

CURRENT_BRANCH=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(not a git repo)")
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   GEO Reporter — DEV MODE (live symlinks)║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""
print_info "Repo:   ${REPO_DIR}"
print_info "Branch: ${CURRENT_BRANCH}"
echo ""

# ----- Replace dirs/files with symlinks -----
link() {
    # link <source-in-repo> <target-in-claude>
    local src="$1"
    local dst="$2"
    if [ -L "$dst" ] || [ -e "$dst" ]; then
        rm -rf "$dst"
    fi
    ln -s "$src" "$dst"
    print_ok "$(basename "$dst") → $(realpath --relative-to="$HOME" "$src" 2>/dev/null || echo "$src")"
}

print_info "Linking main /geo skill components..."
mkdir -p "$INSTALL_DIR"
# The main /geo skill expects SKILL.md, scripts/, schema/ inside its dir.
# Link each piece individually so we can drop in the right source paths.
link "${REPO_DIR}/geo/SKILL.md" "${INSTALL_DIR}/SKILL.md"
link "${REPO_DIR}/scripts" "${INSTALL_DIR}/scripts"
link "${REPO_DIR}/schema" "${INSTALL_DIR}/schema"

echo ""
print_info "Linking sub-skills..."
SKILL_COUNT=0
for skill_dir in "${REPO_DIR}/skills"/*/; do
    if [ -d "$skill_dir" ]; then
        skill_name=$(basename "$skill_dir")
        link "$skill_dir" "${SKILLS_DIR}/${skill_name}"
        SKILL_COUNT=$((SKILL_COUNT + 1))
    fi
done
echo "  → ${SKILL_COUNT} sub-skills linked"

echo ""
print_info "Linking subagents..."
AGENT_COUNT=0
for agent_file in "${REPO_DIR}/agents/"*.md; do
    if [ -f "$agent_file" ]; then
        link "$agent_file" "${AGENTS_DIR}/$(basename "$agent_file")"
        AGENT_COUNT=$((AGENT_COUNT + 1))
    fi
done
echo "  → ${AGENT_COUNT} subagents linked"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              DEV MODE ACTIVE              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
print_warn "Whatever branch you have checked out is what Claude Code runs."
print_warn "Don't run /geo audits on real client work while testing a WIP branch."
echo ""
echo "  Active branch:  ${CURRENT_BRANCH}"
echo "  Repo path:      ${REPO_DIR}"
echo ""
echo "  Switch branches anytime — symlinks follow your checkout:"
echo "    git fetch origin pull/15/head:pr-15"
echo "    git checkout pr-15"
echo ""
echo "  Revert to clean install:"
echo "    ./dev-unlink.sh"
echo ""
