# mcorectl

A command-line interface for [MeshCore](https://github.com/ripplebiz/MeshCore) LoRa mesh networks, built on top of the [meshcore Python library](https://pypi.org/project/meshcore/).

Supports messaging, live packet monitoring, traces, neighbour table queries, remote node status, and remote admin commands.

## Requirements

```
pip install meshcore
```

A MeshCore companion radio node connected via USB serial (default `/dev/ttyUSB0`).

## Usage

```
mcorectl [--port PORT] <command> [options]
```

### Contacts & discovery

```bash
# List all known contacts
mcorectl contacts

# Fetch neighbour table from a relay (repeaters only, by design)
mcorectl neighbours <key_prefix>

# Discover the mesh route to a contact
mcorectl route <key_prefix>
```

### Messaging

```bash
# Send a message to a contact
mcorectl send <key_prefix> "Hello"

# Fetch and print all pending (buffered) messages
mcorectl recv

# Live message monitor (Ctrl+C to stop)
mcorectl listen
```

### Advertising

```bash
# Send a zero-hop advert from the local node
mcorectl advert

# Send a flood advert
mcorectl advert --flood
```

### Tracing

```bash
# Send a trace and print result (exits 0 if reachable, 1 if not)
mcorectl trace <path>

# Verbose mode: print each hop as it arrives
mcorectl trace <path> -v
```

The path is a comma-separated list of 1-byte key prefixes for each hop, including the return path. For example, to trace via a relay to a target and back: `78,64,78`. REACHABLE means the full path completed right now.

Use the exit code to build a polling loop in shell:

```bash
# Wait until reachable, then query the target's neighbour table
while ! mcorectl trace 78,64,78; do
    sleep 900
done && mcorectl neighbours 64
```

### Live RX log

```bash
# Print all received packets to terminal
mcorectl rxlog

# Also write to a file (appends)
mcorectl rxlog --log rxlog.txt
```

Shows packet type, RSSI, SNR, sender name (for adverts), relay node (for relayed adverts), and hop SNR chain.

### Node status & stats

```bash
# Fetch status from a remote node (uptime, battery, packet counts)
mcorectl status <key_prefix>

# Fetch telemetry (voltage, temperature) from a remote node
mcorectl telemetry <key_prefix>

# Show radio and packet stats for the local node
mcorectl stats
```

### Remote admin

```bash
# Login and run a command on a remote node
mcorectl admin <key_prefix> advert --password <password>
mcorectl admin <key_prefix> reboot --password <password>
mcorectl admin <key_prefix> "set guest.password hello" --password <password>
```

The node's text reply is printed. For `reboot`, no reply is expected (the node reboots before it can respond).

## Notes

- The serial port (`/dev/ttyUSB0`) can only be held by one process at a time. Stop `rxlog` or `listen` before running other commands.
- The neighbour table only contains repeater-type nodes — mobile/client nodes are excluded by the firmware by design.
- `trace` exits with code 0 (reachable) or 1 (not), making it usable directly in shell conditions and loops.

## Bash completion

Source the completion script once, or add it to `~/.bashrc` to load it automatically:

```bash
source /path/to/mcorectl_completion.bash
```

Completes: subcommand names, per-subcommand flags, `/dev/tty*` devices for `--port`, filenames for `--log`, and `advert`/`reboot` for `admin`.

## Files

| File | Description |
|------|-------------|
| `mcorectl` | Main CLI tool |
| `mcorectl_completion.bash` | Bash completion script |
