"""ContactsMixin for the mcorechat App."""

from .common import *
from . import theme


class ContactsMixin:
    async def trace_command(self, arg: str):
        """/trace hop,hop,... where a hop is a 1-byte hex hash or a repeater name."""
        toks = [t for t in arg.replace(',', ' ').split() if t]
        if not toks:
            self.status = 'usage: /trace <hop,hop,...>  (hex hash or repeater name)'
            return
        if not self.need_radio():
            return
        route = []
        for t in toks:
            if len(t) == 2 and all(ch in '0123456789abcdefABCDEF' for ch in t):
                route.append(t.lower())
                continue
            hits = [c for c in self.contacts().values()
                    if c.get('type') in (2, 3) and t.lower() in c.get('adv_name', '').lower()]
            if len(hits) != 1:
                self.status = (f'no repeater matches "{t}"' if not hits
                               else f'"{t}" is ambiguous ({len(hits)} repeaters)')
                return
            route.append(hits[0]['public_key'][:2])
        self.status = 'tracing...'
        self.dirty = True

        async def go():
            lines = [f'path: {" > ".join(route)}', ''] + await self.run_trace(route)
            self.show('Trace', lines)
            self.status = 'trace done'
        asyncio.create_task(self.guarded(go()))

    CONTACT_ACTIONS = (
        ('Details', 'details'), ('Ping (zero hop)', 'ping'), ('Trace path', 'trace'),
        ('Discover route', 'discover'), ('Set path...', 'setpath'),
        ('Reset path', 'resetpath'), ('Remove contact', 'remove'),
    )

    def menu_actions(self) -> tuple:
        key = self.selected or ('x',)
        if key[0] == 'c':
            return self.chan_actions(key)
        if key[0] in ('l', 'r'):
            return (('Browse lines' if key[0] == 'l' else 'Browse packets', 'browse'), ('Clear', 'clear'))
        return self.contact_menu_actions()

    def contact_menu_actions(self) -> tuple:
        c = self.selected_contact() or {}
        fav = ('Remove favorite' if c.get('public_key', '')[:12] in self.favorites
               else 'Add favorite', 'favorite')
        acts = list(self.CONTACT_ACTIONS)
        acts.insert(1, fav)
        if c.get('type') == 2:
            return tuple(acts)
        # only repeaters/rooms answer traces, so no ping for plain clients
        return (('Chat', 'chat'),) + tuple(a for a in acts if a[1] != 'ping')

    def selected_contact(self) -> dict | None:
        key = self.selected
        if not key or key[0] != 'd':
            return None
        return next((v for k, v in self.contacts().items() if k.startswith(key[1])), None)

    def open_contact_menu(self):
        """Context menu for whatever is selected in the list: channel, contact, Log or Radio."""
        key = self.selected
        if key is None:
            self.status = 'nothing selected'
        elif key[0] == 'd' and self.selected_contact() is None:
            self.status = 'not in the contact list'
        else:
            self.cmenu_open, self.cmenu_sel = True, 0

    async def item_action(self, action: str):
        key = self.selected
        if key is None:
            return
        if key[0] == 'd':
            await self.contact_action(action)
            return
        if action == 'chat':
            self.focus = 'input'
        elif action == 'browse':
            self.focus, self.msg_sel = 'msgs', max(0, len(self.history.get(key, [])) - 1)
        elif action == 'clear':
            self.history[key] = []
            self.unread.pop(key, None)
            self.status = f'cleared {self.name_for(key)}'
        elif action in ('notify', 'keep', 'people', 'block', 'rename'):
            await self.channel_action(action, key)
        elif action == 'chdetails':
            self.show(f'Channel: {self.name_for(key)}', self.channel_details(key[1]))
        elif action == 'chremove':
            if self.need_radio():
                name = self.name_for(key)
                self.confirm_remove = {'label': f'Remove channel {name}',
                                       'run': lambda: self.apply_remove_channel(key[1], name)}
        self.dirty = True

    def channel_details(self, idx: int) -> list[str]:
        name = next((n for i, n in self.channels if i == idx), '?')
        secret = self.chan_secrets.get(idx, '')
        rows = [('Name', name), ('Slot', str(idx))]
        if name.startswith('#'):
            rows.append(('Kind', 'public hashtag channel (key derived from the name)'))
            rows.append(('Join with', f'/channel {name}'))
        else:
            rows.append(('Kind', 'private channel'))
            rows.append(('Secret', secret or '-'))
            if secret:
                rows.append(('Join with', f'/channel {name} {secret}'))
        out = []
        for a, b in rows:
            lines = textwrap.wrap(b, 52, break_long_words=True) or ['']
            out.append(f'{a + ":":<12}{lines[0]}')
            out += [' ' * 12 + l for l in lines[1:]]
        if secret and not name.startswith('#'):
            out += ['', 'Anyone with this secret can read and post in the channel.']
        return out

    async def apply_remove_channel(self, idx: int, name: str):
        if not self.need_radio():
            return
        async with self.radio_lock:
            r = await self.mc.commands.set_channel(idx, '', bytes(16))
        if r.type == EventType.ERROR:
            self.status = f'remove failed: {describe_error(r.payload)}'
            return
        self.history.pop(('c', idx), None)
        self.chan_secrets.pop(idx, None)
        await self.load_channels()
        self.status = f'removed channel {name}'
        ents = self.entries()
        if ents:
            self.select(ents[0][0])

    def last_signal(self, c: dict) -> tuple | None:
        """Newest (time, snr, rssi, source) heard from this contact: a message or an advert."""
        key = c['public_key'][:12]
        best = self.signal.get(key)
        for m in reversed(self.history.get(('d', key), [])):
            if not m.mine and ('SNR' in m.info or 'RSSI' in m.info):
                if not best or m.recv > best[0]:
                    best = (m.recv, m.info.get('SNR'), m.info.get('RSSI'), 'message')
                break
        return best

    def contact_details(self, c: dict) -> list[str]:
        fmt = lambda t: datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S') if t else 'never'
        n = c.get('out_path_len', -1)
        if n in (-1, 255):
            route = 'flood (no stored path)'
        elif n == 0:
            route = 'direct'
        else:
            route = f'{n} hop(s): ' + ' > '.join(
                self.hop_name(h) for h in self.hops_of(c.get('out_path', ''), n))
        rows = [('Name', c.get('adv_name', '?')),
                ('Type', NODE_TYPES.get(c.get('type'), '?')),
                ('Public key', c['public_key']),
                ('Last advert', fmt(c.get('last_advert', 0))),
                ('Route', route)]
        sig = self.last_signal(c)
        if sig:
            when, snr, rssi, src = sig
            parts = ([f'SNR {snr} dB'] if snr is not None else []) + \
                    ([f'RSSI {rssi} dBm'] if rssi is not None else [])
            rows.append(('Signal', f'{", ".join(parts)} ({src}, {hhmm(when)})'))
        lat, lon = c.get('adv_lat'), c.get('adv_lon')
        if lat or lon:
            rows.append(('Position', f'{lat:.5f}, {lon:.5f}'))
        out = []
        for a, b in rows:
            lines = textwrap.wrap(b, 52, break_long_words=True) or ['']
            out.append(f'{a + ":":<14}{lines[0]}')
            out += [' ' * 14 + l for l in lines[1:]]
        return out

    async def run_trace(self, hops: list[str]) -> list[str]:
        """Send a trace over the given 1-byte hop hashes; returns result lines."""
        async with self.radio_lock:
            r = await self.mc.commands.send_trace(path=','.join(hops))
        if r.type == EventType.ERROR:
            return [f'trace not sent: {describe_error(r.payload)}']
        tag = int.from_bytes(r.payload['expected_ack'], 'little')
        timeout = r.payload.get('suggested_timeout', 10000) / 1000 + 5
        ev = await self.mc.wait_for_event(EventType.TRACE_DATA,
                                          attribute_filters={'tag': tag}, timeout=timeout)
        if ev is None:
            return ['no reply (timed out)',
                    'Only repeaters and room servers answer traces; the node may be out of range.']
        nodes = ev.payload.get('path', [])
        out = []
        for i, nd in enumerate(nodes):
            who = self.hop_name(nd['hash']) if 'hash' in nd else 'this radio'
            out.append(f'hop {i + 1}: {who:<30} SNR {nd["snr"]:.2f} dB' if 'snr' in nd
                       else f'hop {i + 1}: {who}')
        complete = sum('snr' in nd for nd in nodes) >= len(hops)
        out.append('' if out else 'empty reply')
        out.append('REACHABLE' if complete else 'incomplete path')
        return out

    async def contact_action(self, action: str):
        c = self.selected_contact()
        if c is None:
            return
        name = c.get('adv_name', '?')
        if action == 'chat':
            self.focus = 'input'
            self.dirty = True
            return
        if action == 'details':
            self.show(f'Contact: {name}', self.contact_details(c))
            return
        if action == 'favorite':
            k = c['public_key'][:12]
            self.favorites ^= {k}
            self.save_config()
            self.status = f'{name} {"added to" if k in self.favorites else "removed from"} favorites'
            self.dirty = True
            return
        if action == 'remove':
            self.confirm_remove = {'label': f'Remove {name}', 'run': lambda: self.apply_remove(c)}
            self.dirty = True
            return
        if action == 'setpath':
            self.ask = {'label': f'New path for {name} (hex hops, e.g. 78,64; empty = direct)',
                        'text': '', 'cb': self.apply_set_path, 'contact': c}
            self.dirty = True
            return
        if not self.need_radio():
            return
        asyncio.create_task(self.guarded(self.contact_radio_action(action, c)))

    async def contact_radio_action(self, action: str, c: dict):
        name, key = c.get('adv_name', '?'), c['public_key']
        n = c.get('out_path_len', -1)
        hops = self.hops_of(c.get('out_path', ''), n) if n not in (-1, 255) else []
        relay = c.get('type') in (2, 3)
        if action == 'ping':
            self.status = f'pinging {name}...'
            self.dirty = True
            lines = await self.run_trace([key[:2]])
            self.show(f'Ping: {name}', lines)
        elif action == 'trace':
            if not hops and not relay:
                self.status = 'no stored path to trace (try Discover route)'
                return
            route = hops + ([key[:2]] if relay else []) + hops[::-1]
            self.status = f'tracing {name}...'
            self.dirty = True
            lines = [f'path: {" > ".join(route)}', ''] + await self.run_trace(route)
            self.show(f'Trace: {name}', lines)
        elif action == 'discover':
            self.status = f'discovering route to {name}...'
            self.dirty = True
            async with self.radio_lock:
                ev = await self.mc.commands.send_path_discovery_sync(c, min_timeout=15)
            if not ev:
                self.show(f'Route: {name}', ['no response'])
                return
            p = ev.payload
            lines = []
            for label, k in (('Out', 'out_path'), ('In', 'in_path')):
                cnt = p.get(f'{k}_len', 0)
                hs = self.hops_of(p.get(k, ''), cnt)
                lines.append(f'{label}: {cnt} hop(s)' + (': ' + ' > '.join(self.hop_name(h) for h in hs) if hs else ''))
            self.show(f'Route: {name}', lines)
            self.status = 'route discovered'
        elif action == 'resetpath':
            async with self.radio_lock:
                r = await self.mc.commands.reset_path(key)
            self.status = (f'path reset for {name}' if r.type != EventType.ERROR
                           else f'reset failed: {describe_error(r.payload)}')
        self.dirty = True

    async def apply_set_path(self, text: str, c: dict):
        parts = [p for p in text.replace(' ', '').lower().replace(',', ' ').split() if p]
        if any(len(p) != 2 or any(ch not in '0123456789abcdef' for ch in p) for p in parts):
            self.status = 'path must be 1-byte hex hops, e.g. 78,64'
            return
        if not self.need_radio():
            return
        async with self.radio_lock:
            r = await self.mc.commands.change_contact_path(c, ''.join(parts))
        self.status = (f'path set for {c.get("adv_name", "?")}' if r.type != EventType.ERROR
                       else f'set path failed: {describe_error(r.payload)}')

    async def apply_remove(self, c: dict):
        if not self.need_radio():
            return
        async with self.radio_lock:
            r = await self.mc.commands.remove_contact(c['public_key'])
        if r.type == EventType.ERROR:
            self.status = f'remove failed: {describe_error(r.payload)}'
            return
        self.mc.contacts.pop(c['public_key'], None)
        self.status = f'removed {c.get("adv_name", "?")}'
        ents = self.contact_entries() or self.entries()
        if ents:
            self.select(ents[0][0])

    async def handle_cmenu_key(self, k):
        n = len(self.menu_actions())
        if k in ('\x1b', curses.KEY_F7):
            self.cmenu_open = False
        elif k == curses.KEY_UP:
            self.cmenu_sel = max(0, self.cmenu_sel - 1)
        elif k == curses.KEY_DOWN:
            self.cmenu_sel = min(n - 1, self.cmenu_sel + 1)
        elif k == '\n':
            act = self.menu_actions()[self.cmenu_sel][1]
            self.cmenu_open = act in ('notify', 'keep')      # settings that cycle keep the menu open
            await self.item_action(act)
        elif isinstance(k, str) and len(k) == 1 and ord(k) in (CTRL_Q, CTRL_C):
            self.quit = True
        self.dirty = True

    async def handle_ask_key(self, k):
        a = self.ask
        if k == '\x1b':
            self.ask = None
        elif k == '\n':
            self.ask = None
            await a['cb'](a['text'], a['contact'])
        elif k in ('\x7f', '\b') or k == curses.KEY_BACKSPACE:
            a['text'] = a['text'][:-1]
        elif isinstance(k, str) and k.isprintable():
            a['text'] += k
        self.dirty = True

    def draw_cmenu(self, scr, h, w):
        bw = min(w - 2, 40)
        bh = len(self.menu_actions()) + 3
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for y in range(bh):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        scr.addnstr(y0, x0 + 1, self.name_for(self.selected), bw - 2, theme.REV | curses.A_BOLD)
        for i, (label, _) in enumerate(self.menu_actions()):
            attr = theme.SEL if i == self.cmenu_sel else theme.REV
            scr.addnstr(y0 + 1 + i, x0 + 1, label.ljust(bw - 2), bw - 2, attr)
        scr.addnstr(y0 + bh - 1, x0 + 1, 'Enter select · Esc close', bw - 2,
                    theme.REV | curses.A_DIM)
        curses.curs_set(0)

    def draw_ask(self, scr, h, w):
        a = self.ask
        bw = min(w - 2, 70)
        y0, x0 = max(0, h // 2 - 2), max(0, (w - bw) // 2)
        for y in range(4):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        scr.addnstr(y0, x0 + 1, a['label'], bw - 2, theme.REV | curses.A_BOLD)
        scr.addnstr(y0 + 1, x0 + 1, (a['text'] + '_').ljust(bw - 2), bw - 2, theme.REV)
        scr.addnstr(y0 + 3, x0 + 1, 'Enter apply · Esc cancel', bw - 2, theme.REV | curses.A_DIM)
        curses.curs_set(0)
