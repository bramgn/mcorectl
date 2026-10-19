"""MessagingMixin for the mcorechat App."""

from .common import *
from . import theme


class MessagingMixin:
    def on_contact_msg(self, event):
        p = event.payload
        prefix = p.get('pubkey_prefix', '')[:12]
        c = self.mc.get_contact_by_key_prefix(prefix) if prefix else None
        who = c['adv_name'] if c else prefix[:8]
        self.add(('d', prefix), Msg(p.get('sender_timestamp', 0), who, p.get('text', ''),
                                    recv=int(datetime.now().timestamp()), info=dict(p)))

    def on_chan_msg(self, event):
        p = event.payload
        # channel text already arrives as "sender: message"
        key = ('c', p.get('channel_idx', 0))
        msg = Msg(p.get('sender_timestamp', 0), '', p.get('text', ''),
                  recv=int(datetime.now().timestamp()), info=dict(p))
        if self.is_blocked(key, self.sender_of(msg)):
            return
        self.add(key, msg)

    def on_ack(self, event):
        m = self.pending_acks.pop(event.payload.get('code', ''), None)
        if m:
            m.status = 'acked'
            self.dirty = True

    async def send(self, text: str):
        key = self.selected
        if key in (RX_KEY, LOG_KEY):
            self.status = 'this view is read-only: pick a channel or contact to send'
            return
        if key is None or not text or not self.need_radio():
            return
        c = self.selected_contact()
        if c and c.get('type') == 2:                 # repeaters take commands, not chat
            await self.send_admin(text)
            return
        now = int(datetime.now().timestamp())
        msg = Msg(now, 'me', text, mine=True, recv=now)
        self.add(key, msg)
        await self.deliver(key, msg)

    async def transmit(self, key: tuple, msg: Msg, contact: dict | None, attempt: int = 0):
        """One send to the radio; retried when the radio rejects it (busy / queue full)."""
        async with self.radio_lock:
            for n in range(self.retries + 1):
                if key[0] == 'c':
                    r = await self.mc.commands.send_chan_msg(key[1], msg.text, msg.ts)
                else:
                    r = await self.mc.commands.send_msg(contact, msg.text, msg.ts, attempt)
                if r.type != EventType.ERROR:
                    break
                log.warning('send attempt %d to %s failed: %s %s', n + 1,
                            self.name_for(key), describe_error(r.payload), r.payload)
                if n < self.retries:
                    await asyncio.sleep(1)
        return r

    def expect_ack(self, msg: Msg, payload: dict):
        code = payload.get('expected_ack')
        if code:
            self.pending_acks[code if isinstance(code, str) else code.hex()] = msg

    async def deliver(self, key: tuple, msg: Msg):
        contact = None
        if key[0] == 'd':
            contact = self.mc.get_contact_by_key_prefix(key[1])
            if contact is None:
                msg.status = 'failed'
                self.status = 'unknown contact'
                self.dirty = True
                return
        r = await self.transmit(key, msg, contact)
        if r.type in (EventType.MSG_SENT, EventType.OK):      # channel sends are answered with a plain OK
            msg.status = 'sent'
            msg.info = dict(r.payload)
            if key[0] == 'd':
                self.expect_ack(msg, r.payload)
                if self.retries:
                    asyncio.create_task(self.guarded(self.watch_ack(key, msg)))
        else:
            msg.status = 'failed'
            self.status = f'send failed: {describe_error(r.payload)}'
        self.dirty = True

    async def watch_ack(self, key: tuple, msg: Msg):
        """Resend an unacknowledged direct message up to `retries` times, then mark it failed."""
        for attempt in range(self.retries + 1):
            wait = msg.info.get('suggested_timeout', 10000) / 1000 + 2
            for _ in range(int(wait * 2)):
                await asyncio.sleep(0.5)
                if msg.status != 'sent' or self.mc is None:
                    return
            if attempt == self.retries:
                break
            contact = self.mc.get_contact_by_key_prefix(key[1])
            if contact is None:
                break
            self.status = f'no ack from {contact.get("adv_name", "?")}, retry {attempt + 1}/{self.retries}'
            self.dirty = True
            r = await self.transmit(key, msg, contact, attempt + 1)
            if r.type == EventType.ERROR:
                break
            msg.info.update(r.payload)
            self.expect_ack(msg, r.payload)
        if msg.status == 'sent':
            msg.status = 'failed'
            self.status = 'no acknowledgement received'
            self.dirty = True

    def do_search(self, q: str):
        if not q:
            self.status = 'usage: /search <text>'
            return
        hits = []
        for key, msgs in self.history.items():
            if not key or key in (RX_KEY, LOG_KEY):
                continue
            for i, m in enumerate(msgs):
                if q.lower() in m.text.lower():
                    hits.append((m.recv or m.ts, key, i, m))
        hits.sort(key=lambda h: -h[0])
        if not hits:
            self.status = f'no messages match "{q}"'
            return
        self.search = {'q': q, 'hits': hits[:200], 'sel': 0, 'total': len(hits)}

    def handle_search_key(self, k):
        sr = self.search
        n = len(sr['hits'])
        if k in ('\x1b', 'q'):
            self.search = None
        elif k == curses.KEY_UP:
            sr['sel'] = max(0, sr['sel'] - 1)
        elif k == curses.KEY_DOWN:
            sr['sel'] = min(n - 1, sr['sel'] + 1)
        elif k == curses.KEY_PPAGE:
            sr['sel'] = max(0, sr['sel'] - 10)
        elif k == curses.KEY_NPAGE:
            sr['sel'] = min(n - 1, sr['sel'] + 10)
        elif k == '\n':
            _, key, i, _m = sr['hits'][sr['sel']]
            self.search = None
            self.select(key)
            self.focus, self.msg_sel = 'msgs', i
        elif isinstance(k, str) and len(k) == 1 and ord(k) in (CTRL_Q, CTRL_C):
            self.quit = True
        self.dirty = True

    def draw_search(self, scr, h, w):
        sr = self.search
        bw = min(w - 2, 78)
        bh = min(h - 2, len(sr['hits']) + 3)
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for y in range(bh):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        shown = len(sr['hits'])
        more = f' (first {shown} of {sr["total"]})' if sr['total'] > shown else ''
        scr.addnstr(y0, x0 + 1, f'Search "{sr["q"]}": {sr["total"]} match(es){more}', bw - 2, theme.REV | curses.A_BOLD)
        rows = bh - 3
        top = max(0, min(sr['sel'] - rows // 2, shown - rows))
        for i, (_, key, _idx, m) in enumerate(sr['hits'][top:top + rows]):
            who = f'{self.name_for(key)}: ' if key else ''
            line = f'{hhmm(m.recv or m.ts)} {who}{m.who + ": " if m.who and m.who != "me" else ""}{m.text}'
            attr = theme.SEL if top + i == sr['sel'] else theme.REV
            scr.addnstr(y0 + 1 + i, x0 + 1, line.replace('\n', ' ').ljust(bw - 2), bw - 2, attr)
        scr.addnstr(y0 + bh - 1, x0 + 1, 'Enter jump to message · Esc close', bw - 2, theme.REV | curses.A_DIM)
        curses.curs_set(0)

    def message_details(self, m: Msg) -> list[str]:
        key = self.selected
        info = m.info
        fmt = lambda t: datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S') if t else '-'
        rows: list[tuple[str, str]] = []
        me = (self.mc.self_info or {}).get('name', 'me') if self.mc else 'me'
        text = m.text
        if key and key[0] == 'c':
            chan = self.name_for(key)
            if m.mine:
                rows += [('From', f'{me} (you)'), ('To', f'channel {chan}')]
            else:
                sender, sep, rest = text.partition(': ')
                if sep:
                    rows.append(('From', sender))
                    text = rest
                rows.append(('Channel', f'{chan} (slot {key[1]})'))
        elif key:
            c = next((v for k2, v in self.contacts().items() if k2.startswith(key[1])), None)
            peer = self.name_for(key)
            if m.mine:
                rows += [('From', f'{me} (you)'), ('To', peer)]
            else:
                rows.append(('From', peer))
            rows.append(('Key', c['public_key'] if c else key[1]))
            if c:
                rows.append(('Node type', NODE_TYPES.get(c.get('type'), '?')))
        if m.mine:
            rows.append(('Sent', fmt(m.ts)))
            rows.append(('Status', {'sent': 'sent to radio (no ack yet)',
                                    'acked': 'delivered (ack received)',
                                    'failed': 'failed (press r in the message list to resend)'}.get(m.status, m.status or '-')))
        elif m.info:
            rows.append(('Sent (sender clock)', fmt(info.get('sender_timestamp', 0))))
            rows.append(('Received', fmt(m.recv)))
            plen = info.get('path_len')
            if plen is not None:
                rows.append(('Route', 'direct' if plen == 255 else f'{plen} hop(s)'))
            for label, k, unit in (('SNR', 'SNR', ' dB'), ('RSSI', 'RSSI', ' dBm')):
                if k in info:
                    rows.append((label, f'{info[k]}{unit}'))
            if info.get('path'):
                rows.append(('Path', info['path']))
            if 'txt_type' in info:
                rows.append(('Text type', {0: 'plain', 1: 'command', 2: 'signed'}.get(
                    info['txt_type'], str(info['txt_type']))))
        else:
            rows.append(('Note', 'local message (not from the radio)'))
        out = [f'{a + ":":<22}{b}' for a, b in rows]
        out += ['', 'Message:']
        out += textwrap.wrap(text, 64) or ['']
        return out

    def handle_msg_focus_key(self, k) -> bool:
        """Keys while the message list has focus; returns False to fall through to the input."""
        msgs = self.history.get(self.selected, [])
        page = max(1, self.last_body_h // 2)
        if k == '\t':
            self.focus = 'side'
        elif k == '\x1b':
            self.focus = 'input'
        elif k == curses.KEY_UP:
            self.msg_sel = max(0, self.msg_sel - 1)
        elif k == curses.KEY_DOWN:
            self.msg_sel = min(len(msgs) - 1, self.msg_sel + 1)
        elif k == curses.KEY_PPAGE:
            self.msg_sel = max(0, self.msg_sel - page)
        elif k == curses.KEY_NPAGE:
            self.msg_sel = min(len(msgs) - 1, self.msg_sel + page)
        elif k == curses.KEY_HOME:
            self.msg_sel = 0
        elif k == curses.KEY_END:
            self.msg_sel = len(msgs) - 1
        elif k in ('r', 'R') and msgs and msgs[self.msg_sel].mine and \
                msgs[self.msg_sel].status == 'failed' and self.selected not in (RX_KEY, LOG_KEY):
            if self.need_radio():
                m = msgs[self.msg_sel]
                m.status = ''
                self.status = 'resending...'
                asyncio.create_task(self.guarded(self.deliver(self.selected, m)))
        elif k == '\n' and msgs:
            if self.selected == RX_KEY:
                self.show_packet(msgs[self.msg_sel].info)
            elif self.selected == LOG_KEY:
                m = msgs[self.msg_sel]
                self.show('Log entry', [f'Time: {datetime.fromtimestamp(m.ts):%Y-%m-%d %H:%M:%S}', ''] +
                          (textwrap.wrap(m.text, 64) or ['']))
            else:
                self.show('Message details', self.message_details(msgs[self.msg_sel]))
        elif isinstance(k, str) and (k.isprintable() or k == '\x7f'):
            self.focus = 'input'          # start typing: back to the input line
            return False
        else:
            return False
        self.dirty = True
        return True

    def draw_details(self, scr, h, w):
        room = h - 4
        self.details_scroll = max(0, min(self.details_scroll, len(self.details) - room))
        rows = self.details[self.details_scroll:self.details_scroll + room]
        more = len(self.details) > room
        bw = min(w - 2, 78)
        bh = len(rows) + 3
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for y in range(bh):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        scr.addnstr(y0, x0 + 1, self.details_title, bw - 2, theme.REV | curses.A_BOLD)
        verdicts = self.details_title.startswith(('Trace', 'Ping', 'Route'))
        for i, line in enumerate(rows):
            scr.addnstr(y0 + 1 + i, x0 + 1, line, bw - 2,
                        theme.result_attr(line, theme.REV) if verdicts else theme.REV)
        scr.addnstr(y0 + bh - 1, x0 + 1,
                    ('↑/↓ scroll · any other key closes' if more else 'press any key to close')
                    + (' (back to the menu)' if self.details_back else ''), bw - 2,
                    theme.REV | curses.A_DIM)
        curses.curs_set(0)

    def show_packet(self, p: dict):
        """Details window for one RX log packet."""
        ts = p.get('recv_time')
        path, size = p.get('path', ''), p.get('path_hash_size', 1) or 1
        rows = [('Time', datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else '-'),
                ('Type', p.get('payload_typename', '?')),
                ('Route type', p.get('route_typename', '?')),
                ('RSSI', f'{p["rssi"]} dBm' if 'rssi' in p else '-'),
                ('SNR', f'{p["snr"]} dB' if 'snr' in p else '-'),
                ('Length', f'{p.get("payload_length", "-")} bytes')]
        n = p.get('path_len', 0)
        if p.get('payload_typename') == 'TRACE':
            rows.append(('Hop SNRs', ' > '.join(f'{(int(path[i:i + 2], 16) - (256 if int(path[i:i + 2], 16) > 127 else 0)) / 4:.2f}'
                                                for i in range(0, len(path), 2)) or '-'))
        else:
            hops = [path[i:i + size * 2] for i in range(0, len(path), size * 2)]
            rows.append(('Path', (f'{n} hop(s): ' + ' > '.join(self.hop_name(h) for h in hops)) if hops
                         else 'direct' if n == 0 else f'{n} hop(s)'))
        if p.get('transport_code'):
            rows.append(('Transport code', p['transport_code']))
        if 'pkt_hash' in p:
            rows.append(('Packet hash', str(p['pkt_hash'])))
        if p.get('payload_typename') == 'ADVERT':
            key = p.get('adv_key', '')
            c = next((v for v in self.contacts().values() if key and v['public_key'] == key), None)
            rows += [('Advert from', p.get('adv_name') or (c or {}).get('adv_name') or '?'),
                     ('Public key', key),
                     ('Node type', NODE_TYPES.get(p.get('adv_type'), str(p.get('adv_type', '?'))))]
            if p.get('adv_timestamp'):
                rows.append(('Advert time', datetime.fromtimestamp(p['adv_timestamp']).strftime('%Y-%m-%d %H:%M:%S')))
            if p.get('adv_lat') or p.get('adv_lon'):
                rows.append(('Position', f'{p.get("adv_lat", 0):.5f}, {p.get("adv_lon", 0):.5f}'))
                if dist := self.distance_text(p.get('adv_lat', 0), p.get('adv_lon', 0)):
                    rows.append(('Distance', dist))
        for k, label in (('chan_name', 'Channel'), ('message', 'Message'), ('sender_timestamp', 'Sender time'),
                         ('attempt', 'Attempt'), ('chan_hash', 'Channel hash'), ('cipher_mac', 'MAC')):
            if k in p:
                rows.append((label, str(p[k])))
        if p.get('payload'):
            rows.append(('Raw', p['payload']))
        out = []
        for a, b in rows:
            lines = textwrap.wrap(str(b), 52, break_long_words=True) or ['']
            out.append(f'{a + ":":<16}{lines[0]}')
            out += [' ' * 16 + l for l in lines[1:]]
        self.show('Packet', out)

    def on_rx_log(self, event):
        p = event.payload
        ptype = p.get('payload_typename', '?')
        path = p.get('path', '')
        hops = []
        if ptype == 'TRACE':        # path bytes are per-hop SNR, quarter-dB steps
            hops = [f'{(int(path[i:i + 2], 16) - (256 if int(path[i:i + 2], 16) > 127 else 0)) / 4:.2f}dB'
                    for i in range(0, len(path), 2)]
        elif ptype != 'ACK':
            hops = [self.hop_name(path[i:i + 2]) for i in range(0, len(path), 2)]
        extra = ''
        if ptype == 'ADVERT' and p.get('adv_key'):
            self.signal[p['adv_key'][:12]] = (int(datetime.now().timestamp()), p.get('snr'),
                                              p.get('rssi'), 'advert')
        if ptype == 'ADVERT':
            key = p.get('adv_key', '')
            c = self.mc.get_contact_by_key_prefix(key[:8]) if self.mc and key else None
            extra = f'  from {p.get("adv_name") or (c or {}).get("adv_name") or key[:8] or "?"}'
        elif ptype == 'ACK':
            extra = f'  ack {path}'
        if hops:
            extra += '  path ' + ' > '.join(hops)
        now = int(datetime.now().timestamp())
        self.add(RX_KEY, Msg(now, '', f'{ptype:<9} rssi {p.get("rssi", "?"):>4} '
                             f'snr {p.get("snr", "?"):>5}{extra}', recv=now, info=dict(p)), unread=False)

    def render_lines(self, width: int) -> list[tuple[str, int, int]]:
        lines = []
        for n, m in enumerate(self.history.get(self.selected, [])):
            mark = {'sent': ' ·', 'acked': ' ✓', 'failed': ' ✗'}.get(m.status, '')
            body = f'{m.who}: {m.text}' if m.who else m.text
            prefix = f'{hhmm(m.ts)} '
            attr = (theme.NOTE if m.who == '*' else theme.FAIL if m.status == 'failed'
                    else theme.ME if m.mine else curses.A_NORMAL)
            wrapped = textwrap.wrap(body + mark, max(10, width - len(prefix)),
                                    subsequent_indent='  ') or ['']
            for i, w in enumerate(wrapped):
                lines.append(((prefix if i == 0 else ' ' * len(prefix)) + w, attr, n))
        return lines
