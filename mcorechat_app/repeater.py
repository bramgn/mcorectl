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
