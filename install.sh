#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
BASHRC="$HOME/.bashrc"

echo "Installing mcorectl and mcorechat..."

# Python dependencies
if ! python3 -c "import meshcore" 2>/dev/null; then
    echo "Installing meshcore..."
    pip install meshcore
fi
if ! python3 -c "import bleak" 2>/dev/null; then
    echo "Installing bleak..."
    pip install bleak
fi

# Symlink
mkdir -p "$BIN_DIR"
for tool in mcorectl mcorechat; do
    ln -sf "$SCRIPT_DIR/$tool" "$BIN_DIR/$tool"
    chmod +x "$SCRIPT_DIR/$tool"
done

# PATH check
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "Adding $BIN_DIR to PATH in $BASHRC"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$BASHRC"
fi

# Bash completion
COMPLETION_LINE="source \"$SCRIPT_DIR/mcorectl_completion.bash\""
if ! grep -qF "$COMPLETION_LINE" "$BASHRC"; then
    echo "Adding bash completion to $BASHRC"
    echo "$COMPLETION_LINE" >> "$BASHRC"
fi

echo "Done. Run: source ~/.bashrc"
