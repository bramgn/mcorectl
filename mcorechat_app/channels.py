"""ChannelsMixin for the mcorechat App: per-channel notification, retention and block settings."""

from .common import *


class ChannelsMixin:
    NOTIFY_MODES = ('all', 'mentions', 'none')
    KEEP_CHOICES = (50, 100, 250, 500)

    def chan_pref(self, key: tuple) -> dict:
        return self.chan_prefs.get(self.name_for(key), {})

    def chan_set(self, key: tuple, **kw):
        name = self.name_for(key)
        p = self.chan_prefs.setdefault(name, {})
        p.update(kw)
        if p.get('notify', 'all') == 'all':
            p.pop('notify', None)
        if p.get('keep', HISTORY_KEEP) == HISTORY_KEEP:
            p.pop('keep', None)
        if not p.get('blocked'):
            p.pop('blocked', None)
        if not p:
            del self.chan_prefs[name]
        self.save_config()

    def keep_for(self, key: tuple) -> int:
        return self.chan_pref(key).get('keep', HISTORY_KEEP) if key and key[0] == 'c' else HISTORY_KEEP

    @staticmethod
    def sender_of(msg: Msg) -> str:
        """Channel text arrives as 'sender: message'."""
        head, sep, _ = msg.text.partition(': ')
        return head if sep and not msg.mine else ''

    def is_blocked(self, key: tuple, sender: str) -> bool:
        return bool(sender) and sender.lower() in (b.lower() for b in self.chan_pref(key).get('blocked', []))

    def counts_unread(self, key: tuple, msg: Msg) -> bool:
        if key[0] != 'c':
            return True
        mode = self.chan_pref(key).get('notify', 'all')
        if mode == 'mentions':
            me = ((self.mc.self_info or {}).get('name') if self.mc else '') or ''
            return bool(me) and me.lower() in msg.text.lower()
        return mode == 'all'

    def chan_actions(self, key: tuple) -> tuple:
        p = self.chan_pref(key)
        acts = [('Chat', 'chat'),
                (f'Notifications: {p.get("notify", "all")}', 'notify'),
                ('Rename channel...', 'rename'),
                (f'Message retention: last {p.get("keep", HISTORY_KEEP)}', 'keep'),
                ('Participants / blocked', 'people'),
                ('Block / unblock sender...', 'block'),
                ('Details / share key', 'chdetails'),
                ('Clear history', 'clear')]
        if key[1] != 0:
            acts.append(('Remove channel', 'chremove'))
        return tuple(acts)

    def participants(self, key: tuple) -> list[str]:
        seen: dict[str, list] = {}
        for m in self.history.get(key, []):
            s = self.sender_of(m)
            if s:
                e = seen.setdefault(s, [0, 0])
                e[0] += 1
                e[1] = max(e[1], m.recv or m.ts)
        blocked = self.chan_pref(key).get('blocked', [])
        for b in blocked:
            if b.lower() not in (s.lower() for s in seen):
                seen[b] = [0, 0]
        rows = []
        for s, (n, last) in sorted(seen.items(), key=lambda kv: -kv[1][1]):
            tag = '  [blocked]' if s.lower() in (b.lower() for b in blocked) else ''
            rows.append(f'{s}{tag}')
            rows.append(f'    {n} message{"s" if n != 1 else ""}' + (f', last {hhmm(last)}' if last else ''))
        return rows or ['Nobody has posted here yet.']

    async def channel_action(self, action: str, key: tuple):
        name = self.name_for(key)
        if action == 'notify':
            modes = self.NOTIFY_MODES
            mode = modes[(modes.index(self.chan_pref(key).get('notify', 'all')) + 1) % len(modes)]
            self.chan_set(key, notify=mode)
            if mode == 'none':
                self.unread.pop(key, None)
        elif action == 'keep':
            ch = self.KEEP_CHOICES
            cur = self.chan_pref(key).get('keep', HISTORY_KEEP)
            keep = ch[(ch.index(cur) + 1) % len(ch)] if cur in ch else ch[0]
            self.chan_set(key, keep=keep)
            ms = self.history.get(key, [])
            del ms[:-keep]
        elif action == 'people':
            self.show(f'Participants: {name}', self.participants(key))
        elif action == 'block':
            self.ask = {'label': 'Sender to block / unblock (as shown in the channel)', 'text': '',
                        'cb': lambda text, _c: self.toggle_block(key, text), 'contact': None}
        elif action == 'rename':
            self.ask = {'label': f'Rename {name} to', 'text': name,
                        'cb': lambda text, _c: self.apply_rename(key[1], name, text), 'contact': None}

    async def toggle_block(self, key: tuple, who: str):
        who = who.strip()
        if not who:
            return
        blocked = list(self.chan_pref(key).get('blocked', []))
        hit = next((b for b in blocked if b.lower() == who.lower()), None)
        if hit:
            blocked.remove(hit)
            self.status = f'unblocked {hit}'
        else:
            blocked.append(who)
            self.status = f'blocked {who}: their new messages in {self.name_for(key)} are dropped'
        self.chan_set(key, blocked=blocked)
        self.dirty = True

    async def apply_rename(self, idx: int, old: str, new: str):
        new = new.strip()
        if not new or new == old:
            return
        if old.startswith('#') or new.startswith('#'):
            self.status = 'hashtag channels get their key from the name: join the new name with /channel instead'
            return
        secret = self.chan_secrets.get(idx)
        if not secret:
            self.status = 'channel secret unknown: reload (F5) and try again'
            return
        if not self.need_radio():
            return
        async with self.radio_lock:
            r = await self.mc.commands.set_channel(idx, new, bytes.fromhex(secret))
        if r.type == EventType.ERROR:
            self.status = f'rename failed: {describe_error(r.payload)}'
            return
        if old in self.chan_prefs:
            self.chan_prefs[new] = self.chan_prefs.pop(old)
            self.save_config()
        await self.load_channels()
        self.status = f'renamed {old} to {new}'
        self.dirty = True
