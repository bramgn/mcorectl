"""ConnectionMixin for the mcorechat App."""

from .common import *
from . import theme


class ConnectionMixin:
    async def toggle_connection(self):
        if self.connecting:
            return
        if self.mc:
            await self.disconnect()
        else:
            self.open_picker()

    def open_picker(self):
        self.picker_open = True
        self.picker_sel = 0
        self.rescan()

    def close_picker(self):
        self.picker_open = False
        if self.scan_task:
            self.scan_task.cancel()
            self.scan_task = None

    def rescan(self):
        if self.scan_task:
            self.scan_task.cancel()
        labels = {p.device: p.description for p in list_ports.comports()}
        ports = sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
        self.picker_items = [
            ('serial', p, f'{p}  {labels[p]}' if labels.get(p, 'n/a') != 'n/a' else p)
            for p in ports]
        self.picker_note = 'scanning for BLE devices...'
        self.scan_task = asyncio.create_task(self.scan_ble())
        self.dirty = True

    async def scan_ble(self):
        try:
            from bleak import BleakScanner
            devs = await BleakScanner.discover(timeout=5.0, service_uuids=[BLE_UART_UUID])
        except asyncio.CancelledError:
            raise
        except Exception:
            self.picker_note = 'BLE unavailable'
        else:
            self.picker_items += [('ble', d.address, f'BLE {d.address}  {d.name or "?"}')
                                  for d in devs]
            self.picker_note = '' if self.picker_items else 'no devices found'
        self.dirty = True

    def start_auto_connect(self):
        self.connect_to('ble' if self.args.ble else 'serial', self.target())

    def connect_to(self, kind: str, addr: str):
        if kind == 'ble':
            self.args.ble = addr
        else:
            self.args.ble, self.args.port = None, addr
        self.connecting = True
        self.status = f'connecting to {addr}...'
        self.dirty = True
        asyncio.create_task(self.connect())

    async def handle_picker_key(self, k):
        n = len(self.picker_items)
        if k in ('\x1b', curses.KEY_F3):
            self.close_picker()
        elif k == curses.KEY_UP:
            self.picker_sel = max(0, self.picker_sel - 1)
        elif k == curses.KEY_DOWN:
            self.picker_sel = max(0, min(n - 1, self.picker_sel + 1))
        elif k in ('r', 'R'):
            self.rescan()
        elif k == '\n' and n:
            kind, addr, _ = self.picker_items[self.picker_sel]
            self.close_picker()
            self.connect_to(kind, addr)
        elif isinstance(k, str) and len(k) == 1 and ord(k) in (CTRL_Q, CTRL_C):
            self.quit = True
        self.dirty = True

    async def connect(self):
        mc = None
        try:
            cx = (BLEConnection(address=self.args.ble) if self.args.ble
                  else SerialConnection(self.args.port, 115200))
            mc = MeshCore(cx)
            await mc.connect()
            if mc.self_info is None:
                raise RuntimeError('no response from radio')
            self.mc = mc
            # announce protocol v3: the radio then reports SNR with each received message
            r = await mc.commands.send_device_query()
            log.info('device query: %s', 'ok' if r.type != EventType.ERROR else describe_error(r.payload))
            await self.load()
            mc.subscribe(EventType.CONTACT_MSG_RECV, self.on_contact_msg)
            mc.subscribe(EventType.CHANNEL_MSG_RECV, self.on_chan_msg)
            mc.subscribe(EventType.ACK, self.on_ack)
            mc.subscribe(EventType.RX_LOG_DATA, self.on_rx_log)
            for ev in (EventType.NEW_CONTACT, EventType.ADVERTISEMENT, EventType.PATH_UPDATE):
                mc.subscribe(ev, self.on_contacts_changed)
            await self.log_autoadd_config()
            mc.subscribe(EventType.DISCONNECTED, self.on_disconnected)
            await mc.start_auto_message_fetching()
            await self.drain_queue(mc)
            self.save_config()
            self.status = f'connected to {self.target()}'
        except BaseException as e:
            self.mc = None
            if mc is not None:
                try:
                    await mc.disconnect()
                except Exception:
                    pass
            if isinstance(e, asyncio.CancelledError):
                raise
            self.status = f'connect failed: {str(e) or type(e).__name__}'
        finally:
            self.connecting = False
            self.dirty = True

    async def disconnect(self, reason: str = 'disconnected'):
        mc, self.mc = self.mc, None
        if mc is None:
            return
        self.contact_cache = dict(mc.contacts)
        self.pending_acks.clear()
        self.status = reason
        self.dirty = True
        try:
            await mc.disconnect()
        except Exception:
            pass

    async def on_disconnected(self, event):
        # device unplugged / link lost; skip our own manual disconnect
        if self.mc is not None:
            asyncio.create_task(self.disconnect('connection lost'))

    async def load_channels(self) -> int | None:
        """Refresh self.channels from the radio; returns the first free slot, if any."""
        chans, free = [], None
        for idx in range(MAX_CHANNELS):
            async with self.radio_lock:
                r = await self.mc.commands.get_channel(idx)
            if r.type == EventType.ERROR:
                break
            name = r.payload.get('channel_name', '')
            if name:
                chans.append((idx, name))
            elif free is None:
                free = idx
        self.channels = chans
        self.dirty = True
        return free

    async def create_channel(self, arg: str):
        """/channel <name> [secret-hex]: #name = public hashtag channel, otherwise private."""
        if not self.need_radio():
            return
        parts = arg.split()
        if not parts or len(parts) > 2:
            self.status = 'usage: /channel <name> [32-hex-char secret]'
            return
        name = parts[0]
        if len(name.encode()) > 31:
            self.status = 'channel name too long (max 31 bytes)'
            return
        secret = None
        if len(parts) == 2:
            try:
                secret = bytes.fromhex(parts[1])
            except ValueError:
                secret = b''
            if len(secret) != 16:
                self.status = 'secret must be 32 hex characters (16 bytes)'
                return
        elif not name.startswith('#'):
            secret = os.urandom(16)          # private channel: random key, share it by hand
        if any(n == name for _, n in self.channels):
            self.status = f'channel {name} already exists'
            return
        free = await self.load_channels()
        if free is None:
            self.status = 'no free channel slot on the radio'
            return
        async with self.radio_lock:
            r = await self.mc.commands.set_channel(free, name, secret)
        if r.type == EventType.ERROR:
            self.status = f'create channel failed: {describe_error(r.payload)}'
            return
        await self.load_channels()
        self.select(('c', free))
        if name.startswith('#'):
            self.note(f'joined public channel {name} (slot {free})')
        else:
            self.note(f'created channel {name} (slot {free}); secret: '
                      f'{secret.hex() if secret else "derived from name"}')
        self.status = f'channel {name} created'

    async def load(self):
        await self.mc.ensure_contacts()
        await self.load_channels()
        if self.selected is None and (e := self.entries()):
            self.select(e[0][0])
        self.dirty = True

    async def on_contacts_changed(self, event):
        # the library only marks its contact table dirty on adverts; fetch the new entries
        mc = self.mc
        if mc is not None:
            log.info('%s: %s', event.type.value, str(event.payload.get('public_key', ''))[:12])
            try:
                async with self.radio_lock:
                    await mc.ensure_contacts(follow=True)
            except Exception as e:
                log.warning('contact refresh failed: %s', e)
        self.dirty = True

    async def log_autoadd_config(self):
        try:
            r = await self.mc.commands.get_autoadd_config()
            log.info('autoadd config: %s', r.payload)
        except Exception as e:
            log.info('autoadd config unavailable: %s', e)

    async def drain_queue(self, mc):
        """Fetch everything the radio queued while we were away (the library fetches only one)."""
        n = 0
        for _ in range(200):
            async with self.radio_lock:
                r = await mc.commands.get_msg()
            if r.type in (EventType.NO_MORE_MSGS, EventType.ERROR):
                break
            n += 1
            await asyncio.sleep(0.05)
        if n:
            log.info('fetched %d queued message(s)', n)

    async def pick_device(self):
        if self.mc:
            await self.disconnect()
        self.open_picker()

    async def reload(self):
        if self.need_radio():
            self.status = 'reloading...'
            async with self.radio_lock:
                await self.load()
            self.status = f'connected to {self.target()}'

    def draw_picker(self, scr, h, w):
        bw = min(w - 2, 60)
        items = self.picker_items[:max(1, h - 8)]
        bh = len(items) + 4 + (1 if not items or self.picker_note else 0)
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for y in range(bh):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        scr.addnstr(y0, x0 + 1, 'Connect to device', bw - 2, theme.REV | curses.A_BOLD)
        y = y0 + 1
        for i, (_, _, label) in enumerate(items):
            attr = theme.SEL if i == self.picker_sel else theme.REV
            scr.addnstr(y, x0 + 1, label.ljust(bw - 2), bw - 2, attr)
            y += 1
        note = self.picker_note or ('' if items else 'no devices found')
        if note:
            scr.addnstr(y, x0 + 1, note, bw - 2, theme.REV | curses.A_DIM)
        scr.addnstr(y0 + bh - 1, x0 + 1, 'Enter connect · r rescan · Esc cancel', bw - 2,
                    theme.REV | curses.A_DIM)
        curses.curs_set(0)
