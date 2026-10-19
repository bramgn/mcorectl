"""The App class: state and conversation model; behaviour lives in the mixins."""

from .common import *
from . import theme
from .connection import ConnectionMixin
from .messaging import MessagingMixin
from .settings import SettingsMixin
from .contacts import ContactsMixin
from .channels import ChannelsMixin
from .repeater import RepeaterMixin
from .commands import CommandsMixin
from .ui import UiMixin


class App(ConnectionMixin, MessagingMixin, SettingsMixin, ContactsMixin, ChannelsMixin, RepeaterMixin, CommandsMixin, UiMixin):
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
               'theme': self.theme, 'favorites': sorted(self.favorites), 'channels': self.chan_prefs, 'retries': self.retries,
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
        raw = {json.dumps(k): [asdict(m) for m in ms[-self.keep_for(k):] if m.who != '*']
               for k, ms in self.history.items() if k and k not in (RX_KEY, LOG_KEY)}
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
        self.chan_prefs: dict[str, dict] = cfg.get('channels') if isinstance(cfg.get('channels'), dict) else {}
        self.retries = max(0, min(MAX_RETRIES, int(cfg.get('retries', 1))))
        self.theme = cfg.get('theme') if cfg.get('theme') in theme.THEMES else 'blue'
        self.scroll = 0                      # lines scrolled up from bottom
        self.buf = ''
        self.pos = 0
        self.status = 'disconnected'
        self.pending_acks: dict[str, Msg] = {}
        self.dirty = True
        self.repaint = False
        self.quit = False
        self.settings_open = False
        self.set_sel = 0
        self.picker_open = False
        self.focus = 'side'                  # 'side' (list) | 'input' | 'msgs'
        self.chan_secrets: dict[int, str] = {}   # slot -> secret hex, from the last channel load
        self.search: dict | None = None      # /search results overlay
        self.msg_sel = 0
        self.last_body_h = 0
        self.details: list[str] | None = None
        self.details_title = 'Message details'
        self.details_scroll = 0
        self.scr_h = 24
        self.details_back: tuple | None = None   # (key, menu row) of the context menu to return to
        self.menu_origin: tuple | None = None    # set when a menu action may open a window
        self.menu_task: asyncio.Task | None = None
        self.cmenu_open = False
        self.cmenu_sel = 0
        self.advert_menu_open = False
        self.advert_sel = 0
        self.ask: dict | None = None         # single-line input prompt: label/text/cb
        self.confirm_remove: dict | None = None
        self.help_open = False
        self.help_scroll = 0
        self.admin: set[str] = set()         # repeaters / rooms we are logged in to (key prefixes)
        self.node_stats: dict[str, tuple] = {}   # key prefix -> (time, status dict) from the last status request
        self.signal: dict[str, tuple] = {}   # key prefix -> (time, snr, rssi, source) from adverts
        self.radio_lock = asyncio.Lock()     # the library can't tell concurrent replies apart
        self.kill = ''                       # readline kill ring (one slot)
        self.confirm_quit = False
        self.picker_items: list[tuple[str, str, str]] = []   # (kind, address, label)
        self.picker_sel = 0
        self.picker_note = ''
        self.scan_task: asyncio.Task | None = None
        self.set_edit: str | None = None     # text being edited, None when not editing
        LOG.sink = self.on_log_record        # status messages and library logs go to the Log entry
        for rec in list(LOG.records):
            self.on_log_record(rec)
        LOG.records.clear()

    def contact_entries(self) -> list[tuple[tuple, str]]:
        """People first, then repeaters and room servers; each newest first (favourites on top)."""
        out, infra = [], []
        known = set()
        contacts = sorted(self.contacts().values(),
                          key=lambda c: (c['public_key'][:12] not in self.favorites,
                                         -c.get('last_advert', 0)))
        for c in contacts:
            key = ('d', c['public_key'][:12])
            known.add(key)
            is_rep = c.get('type') == 2
            infra_node = c.get('type') in (2, 3)
            fav = key[1] in self.favorites
            if is_rep and not self.show_repeaters and not fav and key not in self.history:
                continue
            tag = '★' if fav else ''
            (infra if infra_node else out).append((key, tag + (c.get('adv_name') or c['public_key'][:8])))
        for key in self.history:
            if key and key[0] == 'd' and key not in known:
                out.append((key, key[1][:8]))
        return out + infra

    def is_infra(self, key: tuple) -> bool:
        """Repeater or room server (listed under Repeaters)."""
        return key[0] == 'd' and any(c.get('type') in (2, 3) for k, c in self.contacts().items()
                                     if k.startswith(key[1]))

    def entries(self) -> list[tuple[tuple, str]]:
        ch = [(('c', i), n) for i, n in self.channels]
        return ch + self.contact_entries() + [(LOG_KEY, 'Log'), (RX_KEY, 'Radio')]

    def name_for(self, key: tuple) -> str:
        for k, n in self.entries():
            if k == key:
                return n
        return key[1][:8] if key[0] == 'd' else f'ch{key[1]}'

    def add(self, key: tuple, msg: Msg, unread: bool = True):
        msgs = self.history.setdefault(key, [])
        msgs.append(msg)
        if key[0] == 'c' and len(msgs) > self.keep_for(key):
            del msgs[0]
        if key in (RX_KEY, LOG_KEY) and len(msgs) > LOG_LINES:
            del msgs[0]
            self.msg_sel = max(0, self.msg_sel - 1)
        if key == self.selected:
            self.scroll = 0
            if self.focus == 'msgs' and self.msg_sel == len(msgs) - 2:
                self.msg_sel = len(msgs) - 1
        elif unread and self.counts_unread(key, msg):
            self.unread[key] = self.unread.get(key, 0) + 1
        self.dirty = True

    def on_log_record(self, record):
        """Log lines become messages in the Log conversation; problems make its sidebar entry light up."""
        text = record.getMessage()
        if record.name != 'mcorechat':
            text = f'{record.name.split(".")[-1]}: {text}'
        if record.levelno >= logging.WARNING:
            text = f'{record.levelname}: {text}'
        problem = record.levelno >= logging.WARNING or (record.name == 'mcorechat' and theme.is_problem(text))
        now = int(record.created)
        for line in text.splitlines() or ['']:
            self.add(LOG_KEY, Msg(now, '', line, recv=now), unread=problem)

    def connection_text(self) -> str:
        if self.connecting:
            return f'connecting to {self.target()}...'
        return f'connected to {self.target()}' if self.mc else 'disconnected'

    def select(self, key: tuple):
        self.selected = key
        if self.focus == 'msgs':
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
        if self.details is None or title != self.details_title:
            self.details_scroll = 0
        if self.menu_origin:                     # opened from a context menu: Esc returns there
            self.details_back, self.menu_origin = self.menu_origin, None
        elif self.details is None:
            self.details_back = None
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
