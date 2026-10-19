"""RepeaterMixin for the mcorechat App: status, telemetry and neighbours of repeaters / room servers."""

from .common import *


def battery_text(mv) -> str:
    """'3912 mV (76%)' for a LiPo cell voltage, roughly."""
    if not mv:
        return 'n/a'
    return f'{mv} mV ({max(0, min(100, round((mv - 3000) / 1200 * 100)))}%)'


def duration_text(secs: int) -> str:
    d, rest = divmod(int(secs), 86400)
    h, rest = divmod(rest, 3600)
    m, s = divmod(rest, 60)
    return (f'{d}d ' if d else '') + f'{h}h {m:02d}m {s:02d}s'


class RepeaterMixin:
    NO_REPLY = ['no reply (timed out)',
                'The node may be out of range, busy, or it may only share this after a login.']

    async def repeater_status(self, c: dict) -> list[str]:
        async with self.radio_lock:
            p = await self.mc.commands.req_status_sync(c, min_timeout=15)
        if not p:
            return self.NO_REPLY
        self.node_stats[c['public_key'][:12]] = (int(time.time()), p)
        rows = [('Uptime', duration_text(p.get('uptime', 0))),
                ('Battery', battery_text(p.get('bat'))),
                ('Noise floor', f'{p.get("noise_floor", "?")} dB'),
                ('Last RSSI / SNR', f'{p.get("last_rssi", "?")} dBm / {p.get("last_snr", "?")} dB'),
                ('TX queue', str(p.get('tx_queue_len', '?'))),
                ('Packets rx / tx', f'{p.get("nb_recv", "?")} / {p.get("nb_sent", "?")}'),
                ('Flood rx / tx', f'{p.get("recv_flood", "?")} / {p.get("sent_flood", "?")}'),
                ('Direct rx / tx', f'{p.get("recv_direct", "?")} / {p.get("sent_direct", "?")}')]
        if p.get('recv_errors') is not None:
            rows.append(('Receive errors', str(p['recv_errors'])))
        return [f'{a + ":":<18}{b}' for a, b in rows]

    async def repeater_telemetry(self, c: dict) -> list[str]:
        async with self.radio_lock:
            lpp = await self.mc.commands.req_telemetry_sync(c, min_timeout=15)
        if lpp is None:
            return self.NO_REPLY
        if not lpp:
            return ['The node shares no telemetry.']
        out = []
        for e in lpp:
            if isinstance(e, dict) and 'type' in e:
                unit = {'temperature': ' °C', 'voltage': ' V', 'humidity': ' %', 'barometer': ' hPa',
                        'luminosity': ' lux', 'current': ' A', 'power': ' W'}.get(str(e['type']), '')
                val = e.get('value')
                if isinstance(val, dict):
                    val = ', '.join(f'{k} {v}' for k, v in val.items())
                out.append(f'{str(e["type"]).replace("_", " ").capitalize() + ":":<18}{val}{unit}'
                           f'   (channel {e.get("channel", "?")})')
            else:
                out.append(str(e))
        return out

    async def repeater_neighbours(self, c: dict) -> list[str]:
        async with self.radio_lock:
            res = await self.mc.commands.fetch_all_neighbours(c, pubkey_prefix_length=8)
        if not res:
            return self.NO_REPLY
        ns = res.get('neighbours', [])
        if not ns:
            return ['The node reports no neighbours.']
        out = [f'{"Node":<26}{"SNR":>8}  Last heard']
        for n in sorted(ns, key=lambda x: x['secs_ago']):
            hit = next((v for v in self.contacts().values() if v['public_key'].startswith(n['pubkey'])), None)
            who = (hit or {}).get('adv_name') or n['pubkey']
            ago = n['secs_ago']
            out.append(f'{who[:25]:<26}{n["snr"]:>5} dB  {ago // 60}m{ago % 60:02d}s ago')
        return out

    COMMAND_HELP = (
        'After logging in, the lines you type in a repeater chat are sent to it as commands and its',
        'answers appear in the same chat. Typical commands (the set depends on the firmware version,',
        'see the MeshCore documentation):',
        '',
        '  ver                   firmware version',
        '  clock                 show the clock;  clock sync  sets it from this computer',
        '  get name | radio | tx | lat | lon     read a setting',
        '  set name <x> | lat <x> | lon <x> ...  change a setting',
        '  advert                send an advert now',
        '  neighbors             list heard neighbours',
        '  password <new>        change the admin password',
        '  reboot                restart the node',
        '',
        'Room servers do not take commands: after logging in you can post to them normally.',
    )

    def ask_login(self, c: dict):
        name = c.get('adv_name', '?')
        self.ask = {'label': f'Password for {name} (empty = guest login)', 'text': '', 'secret': True,
                    'cb': self.apply_login, 'contact': c}
        self.dirty = True

    async def apply_login(self, password: str, c: dict):
        if not self.need_radio():
            return
        name, key = c.get('adv_name', '?'), c['public_key'][:12]
        self.status = f'logging in to {name}...'
        self.dirty = True
        async with self.radio_lock:
            ev = await self.mc.commands.send_login_sync(c, password, min_timeout=15)
        if ev is None or ev.type != EventType.LOGIN_SUCCESS:
            self.status = f'login to {name} failed (no answer, or wrong password)'
            return
        self.admin.add(key)
        role = 'admin' if ev.payload.get('is_admin') else 'guest'
        self.select(('d', key))
        self.note(f'logged in to {name} as {role}.'
                  + (' Lines you type are sent as commands (see Commands in the menu).' if c.get('type') == 2 else ''))
        self.status = f'logged in to {name} as {role}'
        if c.get('type') == 2:
            self.focus = 'input'

    async def apply_logout(self, c: dict):
        key = c['public_key'][:12]
        self.admin.discard(key)
        if self.mc:
            async with self.radio_lock:
                await self.mc.commands.send_logout(c)
        self.status = f'logged out of {c.get("adv_name", "?")}'

    async def send_admin(self, text: str):
        """A line typed in a repeater chat goes out as a CLI command."""
        c = self.selected_contact()
        if c is None or not self.need_radio():
            return
        if c['public_key'][:12] not in self.admin:
            self.status = 'log in first: Enter on the repeater, then "Log in"'
            return
        now = int(datetime.now().timestamp())
        msg = Msg(now, 'me', text, mine=True, recv=now)
        self.add(self.selected, msg)
        async with self.radio_lock:
            r = await self.mc.commands.send_cmd(c, text, now)
        if r.type == EventType.ERROR:
            msg.status = 'failed'
            self.status = f'command not sent: {describe_error(r.payload)}'
        else:
            msg.status = 'sent'
            self.status = 'command sent, waiting for the answer...'
        self.dirty = True
