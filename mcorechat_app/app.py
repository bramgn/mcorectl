"""The App class: state and conversation model; behaviour lives in the mixins."""

from .common import *
from . import theme
from .connection import ConnectionMixin
from .messaging import MessagingMixin
from .settings import SettingsMixin
from .contacts import ContactsMixin
from .commands import CommandsMixin
from .ui import UiMixin


class App(ConnectionMixin, MessagingMixin, SettingsMixin, ContactsMixin, CommandsMixin, UiMixin):
    @property
    def status(self) -> str:
        return self._status

    @property
    def show_repeaters(self) -> bool:
        return self._show_repeaters

    @show_repeaters.setter
    def show_repeaters(self, value: bool):
        self._show_repeaters = value
        self.save_config()

    def save_config(self):
        cfg = {'show_repeaters': self._show_repeaters, 'auto_connect': self.auto_connect,
               'theme': self.theme, 'favorites': sorted(self.favorites), 'retries': self.retries,
               'port': self.args.port, 'ble': self.args.ble}
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except OSError as e:
            log.warning('could not save config: %s', e)

    @staticmethod
    def load_history() -> dict:
        try:
            with open(HISTORY_FILE) as f:
                raw = json.load(f)
            return {(k[0], k[1]): [Msg(**m) for m in ms] for k, ms in
                    ((json.loads(k), v) for k, v in raw.items())}
        except (OSError, ValueError, TypeError, IndexError):
            return {}

    def save_history(self):
        raw = {json.dumps(k): [asdict(m) for m in ms[-HISTORY_KEEP:] if m.who != '*']
               for k, ms in self.history.items() if k and k != RX_KEY}
        raw = {k: v for k, v in raw.items() if v}
        data = json.dumps(raw, default=lambda o: o.hex() if isinstance(o, (bytes, bytearray)) else str(o))
        if data == self._saved_history:
            return
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE + '.tmp', 'w') as f:
                f.write(data)
            os.replace(HISTORY_FILE + '.tmp', HISTORY_FILE)
            self._saved_history = data
        except OSError as e:
            log.warning('could not save history: %s', e)

    @status.setter
    def status(self, text: str):
        self._status = text
        log.info(text)

    def __init__(self, args):
        self.args = args
        self.mc: MeshCore | None = None
        self.connecting = False
        self.contact_cache: dict = {}        # last known contacts, kept after disconnect
        self.channels: list[tuple[int, str]] = []
        self.history: dict[tuple, list[Msg]] = self.load_history()
        self._saved_history = ''
        self.unread: dict[tuple, int] = {}
        self.selected: tuple | None = None
        cfg = load_config()
        self._show_repeaters = bool(cfg.get('show_repeaters', False))
        self.auto_connect = bool(cfg.get('auto_connect', False))
        self.favorites: set[str] = set(cfg.get('favorites', []))     # contact key prefixes (12 hex)
        self.retries = max(0, min(MAX_RETRIES, int(cfg.get('retries', 1))))
        self.theme = cfg.get('theme') if cfg.get('theme') in theme.THEMES else 'blue'
        self.scroll = 0                      # lines scrolled up from bottom
        self.buf = ''
        self.pos = 0
        self.status = 'disconnected'
        self.pending_acks: dict[str, Msg] = {}
        self.dirty = True
        self.quit = False
        self.settings_open = False
        self.set_sel = 0
        self.picker_open = False
        self.focus = 'input'                 # 'input' | 'msgs'
        self.search: dict | None = None      # /search results overlay
        self.msg_sel = 0
        self.last_body_h = 0
        self.details: list[str] | None = None
        self.details_title = 'Message details'
        self.cmenu_open = False
        self.cmenu_sel = 0
        self.advert_menu_open = False
        self.advert_sel = 0
        self.ask: dict | None = None         # single-line input prompt: label/text/cb
        self.confirm_remove: dict | None = None
        self.help_open = False
        self.help_scroll = 0
        self.log_open = False
        self.log_scroll = 0
        self.signal: dict[str, tuple] = {}   # key prefix -> (time, snr, rssi, source) from adverts
        self.radio_lock = asyncio.Lock()     # the library can't tell concurrent replies apart
        self.kill = ''                       # readline kill ring (one slot)
        self.confirm_quit = False
        self.picker_items: list[tuple[str, str, str]] = []   # (kind, address, label)
        self.picker_sel = 0
        self.picker_note = ''
        self.scan_task: asyncio.Task | None = None
        self.set_edit: str | None = None     # text being edited, None when not editing

    def contact_entries(self) -> list[tuple[tuple, str]]:
        """Contacts (plus unknown senders we have history with), newest first."""
        out = []
        known = set()
        contacts = sorted(self.contacts().values(),
                          key=lambda c: (c['public_key'][:12] not in self.favorites,
                                         -c.get('last_advert', 0)))
        for c in contacts:
            key = ('d', c['public_key'][:12])
            known.add(key)
            is_rep = c.get('type') == 2
            fav = key[1] in self.favorites
            if is_rep and not self.show_repeaters and not fav and key not in self.history:
                continue
            tag = '★' if fav else '*' if is_rep else ''
            out.append((key, tag + (c.get('adv_name') or c['public_key'][:8])))
        for key in self.history:
            if key and key[0] == 'd' and key not in known:
                out.append((key, key[1][:8]))
        return out

    def entries(self) -> list[tuple[tuple, str]]:
        ch = [(('c', i), n) for i, n in self.channels]
        return ch + self.contact_entries() + [(RX_KEY, 'RX log')]

    def name_for(self, key: tuple) -> str:
        for k, n in self.entries():
            if k == key:
                return n
        return key[1][:8] if key[0] == 'd' else f'ch{key[1]}'

    def add(self, key: tuple, msg: Msg):
        msgs = self.history.setdefault(key, [])
        msgs.append(msg)
        if key == RX_KEY and len(msgs) > LOG_LINES:
            del msgs[0]
            self.msg_sel = max(0, self.msg_sel - 1)
        if key == RX_KEY and key != self.selected:
            pass                                  # packets don't count as unread
        elif key == self.selected:
            self.scroll = 0
            if self.focus == 'msgs' and self.msg_sel == len(msgs) - 2:
                self.msg_sel = len(msgs) - 1
        else:
            self.unread[key] = self.unread.get(key, 0) + 1
        self.dirty = True

    def select(self, key: tuple):
        self.selected = key
        self.focus = 'input'
        self.unread.pop(key, None)
        self.scroll = 0
        self.dirty = True

    def move(self, delta: int):
        ents = self.entries()
        if not ents:
            return
        keys = [k for k, _ in ents]
        i = keys.index(self.selected) if self.selected in keys else -1
        self.select(keys[max(0, min(len(keys) - 1, i + delta))])

    def contacts(self) -> dict:
        return self.mc.contacts if self.mc else self.contact_cache

    def target(self) -> str:
        return self.args.ble or self.args.port

    def need_radio(self) -> bool:
        if self.mc is None:
            self.status = 'not connected'
            self.dirty = True
            return False
        return True

    def note(self, text: str):
        """Local-only line in the current conversation (never sent)."""
        self.history.setdefault(self.selected, []).append(
            Msg(0, '*', text, mine=True))
        self.scroll = 0
        self.dirty = True

    def hop_name(self, h: str) -> str:
        """Name for a path hash (repeaters preferred, since those are what relay)."""
        hits = [c for c in self.contacts().values() if c['public_key'].startswith(h.lower())]
        hits.sort(key=lambda c: c.get('type') != 2)
        return f'{hits[0]["adv_name"]} ({h})' if hits else h

    @staticmethod
    def hops_of(path_hex: str, n: int) -> list[str]:
        return [path_hex[i:i + 2] for i in range(0, n * 2, 2)]

    def show(self, title: str, lines: list[str]):
        self.details_title, self.details = title, lines
        self.dirty = True

    async def guarded(self, coro):
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception('action failed')
            self.status = f'failed: {e}'
            self.dirty = True
