# mcorectl

A command-line interface for [MeshCore](https://github.com/ripplebiz/MeshCore) LoRa mesh networks, built on top of the [meshcore Python library](https://pypi.org/project/meshcore/).

Supports messaging, live packet monitoring, traces, neighbour table queries, remote node status, and remote admin commands.

## Install

```bash
git clone https://github.com/bramgn/mcorectl
cd mcorectl
./install.sh
source ~/.bashrc
```

The script installs `meshcore` and `bleak` via pip if needed, symlinks `mcorectl` and `mcorechat` (the ncurses client, see below) into `~/.local/bin`, and adds bash completion to `~/.bashrc`.

A MeshCore companion radio node connected via USB serial (default `/dev/ttyUSB0`).

## Usage

```
mcorectl [--port PORT] <command> [options]
mcorectl --ble <ADDRESS> <command> [options]
```

### BLE connection

MeshCore devices that support BLE (e.g. Heltec V3) can be used wirelessly.

**First-time setup** — pair the device once using `bluetoothctl`:

```bash
bluetoothctl
[bluetooth]# agent on
[bluetooth]# scan on
# Wait for your device to appear, then:
[bluetooth]# scan off
[bluetooth]# pair 3C:0F:02:E5:B7:F1   # use your device's address
# Enter the passkey shown on the device when prompted
[bluetooth]# trust 3C:0F:02:E5:B7:F1
[bluetooth]# disconnect 3C:0F:02:E5:B7:F1
[bluetooth]# quit
```

**Connecting** — use `--ble <ADDRESS>` in place of `--port`:

```bash
mcorectl --ble 3C:0F:02:E5:B7:F1 info
mcorectl --ble 3C:0F:02:E5:B7:F1 listen
```

**Tip:** set `MCORECTL_BLE` in your `~/.bashrc` to avoid typing the address every time:

```bash
export MCORECTL_BLE=3C:0F:02:E5:B7:F1
mcorectl contacts   # uses BLE automatically
```

Use `mcorectl list` to discover available serial and BLE devices.

## Command overview

| Command | Local (USB/BLE) | Remote (`key_prefix`) |
|---|---|---|
| `info` | ✓ name, key, uptime, battery, radio settings, pending msgs | — |
| `stats` | ✓ radio & packet statistics | — |
| `set-txpower <dbm>` | ✓ | — |
| `contacts` | ✓ | — |
| `channels` | ✓ | — |
| `channel-send <idx> <msg>` | ✓ | — |
| `advert [--flood]` | ✓ | — |
| `recv` | ✓ drain buffered messages | — |
| `listen` | ✓ live message monitor | — |
| `rxlog [--log file]` | ✓ live LoRa packet log | — |
| `send <prefix> <msg>` | ✓ routes via local node | — |
| `list` | ✓ discover serial/BLE devices | — |
| `status <prefix>` | — | ✓ uptime, battery, packet counts |
| `telemetry <prefix>` | — | ✓ voltage, temperature |
| `neighbours <prefix>` | — | ✓ relay's neighbour table |
| `route <prefix>` | — | ✓ mesh route discovery |
| `trace <path>` | ✓ hop-by-hop reachability test | — |
| `admin <prefix> <cmd>` | — | ✓ advert, reboot, set … |

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
| `install.sh` | Installer: symlinks binary, installs Python deps, sets up completion |

## mcorechat

`mcorechat` is a simple ncurses chat client built on the same library: channel list, contact list,
per-conversation history, unread counts, and send/receive for channels and private messages.

```bash
./mcorechat                  # serial, /dev/ttyUSB0 (or --port / $MCORECHAT_PORT)
./mcorechat --ble <ADDRESS>
./mcorechat --version
```

Up/Down select a conversation, Enter sends (on an empty line it opens the contact menu for a selected contact), PgUp/PgDn scroll, `/advert zero` / `/advert flood` send an advert directly (or pick *Send advert* in the options, `F2`),
`F8` / `/log` selects the **Log** entry and `F9` / `/radio` the **Radio** entry under *Console* in the sidebar (Radio lists every packet the radio hears; Tab to highlight a packet, Enter shows its details), `F2` / `/options` the options (send advert, colour theme, name, TX power, your location, auto add discovered contacts), `F3` pick a device and connect (or disconnect), `^L` repaint the screen, `^Q` quit. The list has the sections Channels, Contacts, Repeaters (repeaters and room servers) and Console. Showing repeaters is an option (`F2` or `/repeaters`); `/reload` re-reads contacts and channels from the radio.

The version (`__version__` in `mcorechat_app/__init__.py`) shows in the title bar and the help window.

The app starts disconnected and never connects on its own; press `F3` to list serial ports and BLE devices and choose one. The serial port / BLE address
can be changed in the options screen (`F2`) before connecting.

Slash commands work in the input line: `/quit` (`/q`), `/connect`, `/disconnect`, `/advert`, `/log` (`/console`), `/clear` (empties the selected conversation, e.g. the Log), `/ping [repeater]` (zero-hop trace to the selected or named repeater, with round-trip time), `/trace 78,64,78` (hex hashes or repeater names), `/reload`,
`/options`, `/repeaters`, `/help`. `F1` or `/help` shows the full key and command list; `F10` quits.
`Tab` completes a command (listing the matches when ambiguous). Start a message with `//` to send a literal leading `/`.

The input line understands the usual readline keys (`^A ^E ^B ^F ^D ^U ^K ^W ^Y`); `^P`/`^N` switch conversation.
The title bar's top-right corner only shows the connection state. Everything else (status messages, usage hints, errors, library log output) goes to the **Log** entry in the sidebar, which lights up like an unread conversation when something goes wrong.

Channels: `/channel #name` joins a public hashtag channel (key derived from the name, like other MeshCore apps).
`/channel name` creates a private channel with a random key and prints the secret in the conversation so you can
share it; `/channel name <32 hex chars>` joins a private channel with a known key. The channel goes into the first
free radio slot (8 max) and is selected.

App-side preferences (show repeaters, last used serial port / BLE address) are saved in
`~/.config/mcorechat/config.json`. Radio-side settings stay on the device.

Focus: the app starts with the list on the left focused. Up/Down move through channels, contacts and the Console entries,
and `Enter` opens the **context menu** of the selected item (channels: see below; contacts: see below; Log and Radio: Browse, Clear). `Tab` moves to the input on the right (typing from the list
does the same), where `Enter` sends. `Tab` again moves to the message list: Up/Down/PgUp/PgDn highlight a message and
`Enter` shows sender, key, times, route, SNR/RSSI, delivery status and the full text. A further `Tab` returns to the list;
`Esc` goes back one step (messages > input > list).

Channel menu: *Chat*; *Notifications* (all / mentions only / none: decides whether new messages light up the channel in the
list; Enter cycles it); *Rename channel* (private channels only, the key stays); *Message retention* (keep the last 50 / 100 /
250 / 500 messages, Enter cycles it); *Participants / blocked* (who has posted, with message counts); *Block / unblock
sender* (type the name as shown in the channel; blocked senders' new messages are dropped); *Details / share key*; *Clear
history* (same as `/clear`); *Remove channel*. These per-channel settings are stored in the config file, keyed by channel name.

Colour themes (`/theme` lists them, `/theme <name>` switches, or press Left/Right on the theme row in the options to step through them live): `blue`, `green`, `amber`,
`light`, `mono`, plus 256-colour themes `vampire`, `fjord`, `sundial`, `harvest`, `shibuya`, `synthwave`, `deepsea`,
`rosewater`, `mossy` and `parchment` (for light terminals). On terminals with fewer than 256 colours they fall back to the
nearest basic colours.

`/reboot` (or *Reboot radio* in the options) restarts the radio after a confirmation; the link drops and you reconnect with `F3`.

Managing a repeater: in its menu choose *Log in (manage)...* and enter the admin password (shown as `*`; empty = guest). Once
logged in, the repeater's chat becomes a console: every line you type is sent to the repeater as a command (`ver`, `clock`,
`advert`, `get name`, `set name ...`, `reboot`, ...; *Commands...* in the menu lists the common ones) and its answer shows up
in the same chat. *Log out* ends the session; the login is also forgotten when you disconnect. The password is never stored.
Room servers use the same login, after which you post to them as usual.

Location: set your own position in the options (`F2`, *Location*, as `lat, lon` in decimal degrees, or `none` to clear). Contact
details and advert packet details then show the distance and compass direction to any node that advertises a position.

Contact menu (`Enter` in the list, `F7` or `/contact`, on a selected contact or repeater): Details, Status / battery (uptime, battery, noise floor, packet counts), Telemetry (voltage, temperature, ... as the node shares them), Neighbours (repeaters only), Ping (zero-hop trace), Trace path
(over the stored path and back), Discover route, Set path, Reset path and Remove contact (asks first). Ping and
trace only get answers from repeaters / room servers.

`mcorechat` keeps message history in `~/.config/mcorechat/history.json` (last 500 messages per conversation, saved every 10 s and on exit).
