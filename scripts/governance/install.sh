#!/usr/bin/env bash
# ==============================================================================
# INSTALL ARCH LINUX ON-DEMAND SYSTEM GOVERNANCE TOOLS
# Installs audit-rules, enforcers, and user shield services into local environment.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Installing User Governance Tools ==="
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/ondemand-optimization"
mkdir -p "$HOME/.config/systemd/user"

cp -f "$SCRIPT_DIR/audit-rules" "$HOME/.local/bin/audit-rules"
cp -f "$SCRIPT_DIR/enforce-user-governance" "$HOME/.local/bin/enforce-user-governance"
chmod +x "$HOME/.local/bin/audit-rules" "$HOME/.local/bin/enforce-user-governance"

cp -f "$SCRIPT_DIR/apply-optimization.sh" "$HOME/.local/share/ondemand-optimization/apply-optimization.sh"
cp -f "$SCRIPT_DIR/rollback-optimization.sh" "$HOME/.local/share/ondemand-optimization/rollback-optimization.sh"
cp -f "$SCRIPT_DIR/enforce-governance.sh" "$HOME/.local/share/ondemand-optimization/enforce-governance.sh"
chmod +x "$HOME/.local/share/ondemand-optimization"/*.sh

cp -f "$REPO_DIR/systemd/system-governance-user-shield.service" "$HOME/.config/systemd/user/system-governance-user-shield.service"

systemctl --user daemon-reload
systemctl --user enable --now system-governance-user-shield.service

echo "[✓] User Governance Tools & Shield Service installed successfully."
echo "To apply root/system-wide optimizations, run:"
echo "  sudo bash ~/.local/share/ondemand-optimization/apply-optimization.sh"
