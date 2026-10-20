"""SettingsMixin for the mcorechat App."""

from .common import *
from . import theme
from .repeater import battery_text


class SettingsMixin:
    SETTINGS = ('info', 'port', 'autoconnect', 'name', 'tx_power', 'location', 'clock', 'advert', 'reboot', 'auto_add', 'repeaters', 'retries', 'theme')

    def setting_rows(self) -> list[tuple[str, str]]:
        si = (self.mc.self_info if self.mc else None) or {}
        onoff = lambda b: 'on' if b else 'off'
        dash = lambda k: str(si[k]) if k in si else '-'
        return [
            ('This radio', 'public key, firmware, battery...'),
            ('BLE address' if self.args.ble else 'Serial port', self.target()),
            ('Connect on startup', onoff(self.auto_connect)),
            ('Device name', dash('name')),
            ('TX power (dBm)', dash('tx_power')),
            ('Location (lat, lon)', self.my_position_text()),
            ('Set radio clock', 'to this computer\'s time'),
            ('Send advert', 'zero hop / flood...'),
            ('Reboot radio', 'asks first'),
            ('Auto add discovered contacts',
             onoff(not si['manual_add_contacts']) if 'manual_add_contacts' in si else '-'),
            ('Show repeaters in list', onoff(self.show_repeaters)),
            ('Send retries', str(self.retries)),
            ('Colour theme', self.theme),
        ]

    def my_position(self) -> tuple[float, float] | None:
        si = (self.mc.self_info if self.mc else None) or {}
        lat, lon = si.get('adv_lat') or 0, si.get('adv_lon') or 0
        return (lat, lon) if lat or lon else None

    def my_position_text(self) -> str:
        if not self.mc:
            return '-'
        pos = self.my_position()
        return f'{pos[0]:.5f}, {pos[1]:.5f}' if pos else 'not set'

    @staticmethod
    def parse_position(text: str) -> tuple[float, float] | None:
        text = text.strip().lower()
        if text in ('none', 'clear', '0'):
            return 0.0, 0.0
        try:
            lat, lon = (float(x) for x in text.replace(',', ' ').split())
        except ValueError:
            return None
        return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None

    def distance_text(self, lat: float, lon: float) -> str | None:
        """'12.3 km NE' from our own position to (lat, lon); None when either is unknown."""
        me = self.my_position()
        if not me or not (lat or lon):
            return None
        p1, p2 = math.radians(me[0]), math.radians(lat)
        dl = math.radians(lon - me[1])
        a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        km = 12742 * math.asin(math.sqrt(a))
        brg = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                      math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)))
        compass = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')[round(brg % 360 / 45) % 8]
        dist = f'{km * 1000:.0f} m' if km < 1 else f'{km:.1f} km' if km < 100 else f'{km:.0f} km'
        return f'{dist} {compass}'

    async def sync_radio_clock(self, force: bool = False):
        """Put the companion radio's clock on this computer's time. The radio stamps adverts and
        commands (such as a repeater's `clock sync`) with its own clock, so a wrong one spreads."""
        try:
            async with self.radio_lock:
                r = await self.mc.commands.get_time()
                if r.type == EventType.ERROR:
                    log.warning('radio clock: could not read it: %s', describe_error(r.payload))
                    return
                diff = r.payload.get('time', 0) - time.time()
                if abs(diff) <= 5:
                    if force:
                        self.status = 'radio clock is already correct'
                    return
                r = await self.mc.commands.set_time(int(time.time()))
        except Exception as e:
            log.warning('radio clock: %s', e)
            return
        if r.type == EventType.ERROR:
            log.warning('radio clock was %+.0f s off and could not be set: %s', diff, describe_error(r.payload))
        else:
            self.status = f'radio clock was {abs(diff):.0f} s {"ahead" if diff > 0 else "behind"}, set to this computer\'s time'

    async def refresh_battery(self):
        """Read the companion's battery for the title bar (a local request, no airtime)."""
        try:
            async with self.radio_lock:
                r = await self.mc.commands.get_bat()
            if r.type != EventType.ERROR:
                self.radio_bat = r.payload.get('level')
                self.dirty = True
        except Exception as e:
            log.warning('battery: %s', e)

    async def radio_info(self):
        """Window with what the connected companion radio says about itself (no airtime)."""
        si = self.mc.self_info or {}
        async with self.radio_lock:
            dev = await self.mc.commands.send_device_query()
            bat = await self.mc.commands.get_bat()
            tm = await self.mc.commands.get_time()
        dev = dev.payload if dev.type != EventType.ERROR else {}
        bat = bat.payload if bat.type != EventType.ERROR else {}
        mv = bat.get('level')
        self.radio_bat = mv
        if tm.type != EventType.ERROR:
            diff = tm.payload.get('time', 0) - time.time()
            clock = 'in sync' if abs(diff) <= 5 else f'{abs(diff):.0f} s {"ahead of" if diff > 0 else "behind"} this computer'
        else:
            clock = '-'
        nc = len(self.contacts())
        rows = [
            ('Name', si.get('name', '-')),
            ('Public key', si.get('public_key', '-')),
            ('Firmware', ' '.join(x for x in (dev.get('ver'), f'({dev["fw_build"]})' if dev.get('fw_build') else '') if x) or '-'),
            ('Board', dev.get('model') or '-'),
            ('Protocol version', str(dev['fw ver']) if 'fw ver' in dev else '-'),
            ('Battery', battery_text(mv)),
        ]
        if 'used_kb' in bat:
            rows.append(('Storage', f'{bat["used_kb"]} / {bat["total_kb"]} kB'))
        rows += [
            ('Radio', f'{si["radio_freq"]:.3f} MHz, BW {si["radio_bw"]:g} kHz, SF{si["radio_sf"]}, CR 4/{si["radio_cr"]}'
             if 'radio_freq' in si else '-'),
            ('TX power', f'{si["tx_power"]} dBm (max {si["max_tx_power"]})' if 'tx_power' in si and 'max_tx_power' in si
             else f'{si.get("tx_power", "-")} dBm'),
            ('Location', self.my_position_text()),
            ('Clock', clock),
            ('Contacts', f'{nc} of {dev["max_contacts"]}' if 'max_contacts' in dev else str(nc)),
        ]
        if 'max_channels' in dev:
            rows.append(('Channels', f'max {dev["max_channels"]}'))
        key = si.get('public_key', '')
        if len(key) == 64:                      # two lines: a phone screen is narrower than 64 characters
            i = next(n for n, r in enumerate(rows) if r[0] == 'Public key')
            rows[i:i + 1] = [('Public key', key[:32]), ('', key[32:])]
        self.show('This radio', [f'{a + ":" if a else "":<18}{b}' for a, b in rows])

    def ask_reboot(self):
        if self.need_radio():
            self.confirm_remove = {'label': 'Reboot the radio (the link drops, reconnect afterwards)',
                                   'run': self.reboot_radio}
            self.dirty = True

    async def reboot_radio(self):
        if not self.need_radio():
            return
        self.status = 'rebooting the radio...'
        try:
            async with self.radio_lock:
                await asyncio.wait_for(self.mc.commands.reboot(), 3)   # the radio may not answer
        except (asyncio.TimeoutError, OSError):
            pass
        await self.disconnect('radio rebooting: connect again in a few seconds (F3)')

    def set_theme(self, name: str):
        self.theme = name
        theme.init_colors(name)
        self.save_config()
        self.dirty = True

    def theme_command(self, arg: str):
        """/theme lists the themes, /theme <name> switches (a unique prefix is enough)."""
        arg = arg.strip().lower()
        if not arg:
            self.show('Colour themes', [f'{"> " if n == self.theme else "  "}{n:<11}{theme.DESCRIPTIONS.get(n, "")}'
                                        for n in theme.THEMES] + ['', 'Switch with /theme <name>.'])
            return
        hits = [n for n in theme.THEMES if n == arg] or [n for n in theme.THEMES if n.startswith(arg)]
        if len(hits) != 1:
            self.status = f'no theme "{arg}" (try /theme for the list)' if not hits else \
                f'"{arg}" is ambiguous: {", ".join(hits)}'
            return
        self.set_theme(hits[0])

    async def apply_setting(self, which: str, text: str | None = None):
        if which == 'info':
            if self.need_radio():
                self.settings_open = False
                await self.radio_info()
            return
        if which == 'clock':
            if self.need_radio():
                await self.sync_radio_clock(force=True)
            return
        if which == 'reboot':
            self.settings_open = False
            self.ask_reboot()
            return
        if which == 'advert':
            self.settings_open = False
            await self.advert()
            return
        if which == 'repeaters':
            self.show_repeaters = not self.show_repeaters
            return
        if which == 'retries':
            self.retries = (self.retries + 1) % (MAX_RETRIES + 1)
            self.save_config()
            self.status = f'send retries: {self.retries}'
            return
        if which == 'theme':
            names = list(theme.THEMES)
            self.set_theme(names[(names.index(self.theme) + 1) % len(names)])
            return
        if which == 'autoconnect':
            self.auto_connect = not self.auto_connect
            self.save_config()
            self.status = f'connect on startup: {"on" if self.auto_connect else "off"}'
            return
        if which == 'port':
            if text:
                if self.args.ble:
                    self.args.ble = text
                else:
                    self.args.port = text
                self.save_config()
                self.status = f'target set to {text} (takes effect on next connect)'
            return
        if not self.need_radio():
            return
        si = self.mc.self_info
        cmds = self.mc.commands
        if which == 'auto_add':
            manual = not si.get('manual_add_contacts', False)
            r = await cmds.set_manual_add_contacts(manual)
            ok_val = ('manual_add_contacts', manual)
        elif which == 'name' and text:
            r = await cmds.set_name(text)
            ok_val = ('name', text)
        elif which == 'location' and text is not None:
            pos = self.parse_position(text)
            if pos is None:
                self.status = 'location: enter "lat, lon" in decimal degrees (e.g. 52.37, 4.89), or "none" to clear'
                return
            r = await cmds.set_coords(*pos)
            ok_val = None
            if r.type != EventType.ERROR:
                self.mc.self_info.update(adv_lat=pos[0], adv_lon=pos[1])
        elif which == 'tx_power' and text:
            try:
                dbm = int(text)
            except ValueError:
                self.status = 'TX power must be a number'
                return
            r = await cmds.set_tx_power(dbm)
            ok_val = ('tx_power', dbm)
        else:
            return
        if r.type == EventType.ERROR:
            self.status = f'setting failed: {describe_error(r.payload)}'
        else:
            if ok_val:
                self.mc.self_info[ok_val[0]] = ok_val[1]   # library may have replaced the dict
            self.status = 'saved'

    async def handle_settings_key(self, k):
        which = self.SETTINGS[self.set_sel]
        if self.set_edit is not None:
            if k == '\n':
                text, self.set_edit = self.set_edit.strip(), None
                await self.apply_setting(which, text)
            elif k == '\x1b':
                self.set_edit = None
            elif k in ('\x7f', '\b') or k == curses.KEY_BACKSPACE:
                self.set_edit = self.set_edit[:-1]
            elif isinstance(k, str) and k.isprintable():
                self.set_edit += k
        elif k in ('\x1b', curses.KEY_F2):
            self.settings_open = False
        elif k == curses.KEY_UP:
            self.set_sel = max(0, self.set_sel - 1)
        elif k == curses.KEY_DOWN:
            self.set_sel = min(len(self.SETTINGS) - 1, self.set_sel + 1)
        elif k in (curses.KEY_LEFT, curses.KEY_RIGHT) and which == 'theme':
            names = list(theme.THEMES)
            step = 1 if k == curses.KEY_RIGHT else -1
            self.set_theme(names[(names.index(self.theme) + step) % len(names)])
        elif k in ('\n', ' '):
            if which in ('port', 'name', 'tx_power', 'location'):
                if which != 'port' and not self.need_radio():
                    return
                self.set_edit = ''
            else:
                await self.apply_setting(which)
        elif isinstance(k, str) and len(k) == 1 and ord(k) in (CTRL_Q, CTRL_C):
            self.quit = True
        self.dirty = True

    ADVERT_CHOICES = (('Zero hop (direct neighbours only)', False),
                      ('Flood (forwarded across the mesh)', True))

    async def advert(self, flood: bool | None = None):
        """Send an advert; with flood=None, ask which kind."""
        if not self.need_radio():
            return
        if flood is None:
            self.advert_menu_open, self.advert_sel = True, 0
            self.dirty = True
            return
        async with self.radio_lock:
            r = await self.mc.commands.send_advert(flood=flood)
        kind = 'flood' if flood else 'zero-hop'
        self.status = (f'{kind} advert sent' if r.type != EventType.ERROR
                       else f'advert failed: {describe_error(r.payload)}')
        self.dirty = True

    async def handle_advert_key(self, k):
        if k == '\x1b':
            self.advert_menu_open = False
        elif k == curses.KEY_UP:
            self.advert_sel = 0
        elif k == curses.KEY_DOWN:
            self.advert_sel = len(self.ADVERT_CHOICES) - 1
        elif k == '\n':
            self.advert_menu_open = False
            await self.advert(self.ADVERT_CHOICES[self.advert_sel][1])
        elif isinstance(k, str) and len(k) == 1 and ord(k) in (CTRL_Q, CTRL_C):
            self.quit = True
        self.dirty = True

    def draw_advert_menu(self, scr, h, w):
        bw = min(w - 2, 44)
        bh = len(self.ADVERT_CHOICES) + 3
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for y in range(bh):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        scr.addnstr(y0, x0 + 1, 'Send advert', bw - 2, theme.REV | curses.A_BOLD)
        for i, (label, _) in enumerate(self.ADVERT_CHOICES):
            attr = theme.SEL if i == self.advert_sel else theme.REV
            scr.addnstr(y0 + 1 + i, x0 + 1, label.ljust(bw - 2), bw - 2, attr)
        scr.addnstr(y0 + bh - 1, x0 + 1, 'Enter send · Esc cancel', bw - 2,
                    theme.REV | curses.A_DIM)
        curses.curs_set(0)

    def draw_settings(self, scr, h, w):
        rows = self.setting_rows()
        bw = min(w - 2, 58)
        bh = len(rows) + 4
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for y in range(bh):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        scr.addnstr(y0, x0 + 1, 'Options', bw - 2, theme.REV | curses.A_BOLD)
        for i, (label, val) in enumerate(rows):
            if i == self.set_sel and self.set_edit is not None:
                val = self.set_edit + '_'
            line = f'{label:<31}{val}'
            attr = theme.SEL if i == self.set_sel else theme.REV
            scr.addnstr(y0 + 1 + i, x0 + 1, line.ljust(bw - 2), bw - 2, attr)
        hint = 'Enter save · Esc cancel' if self.set_edit is not None else \
            ('←/→ theme · ' if self.SETTINGS[self.set_sel] == 'theme' else '') + 'Enter change · Esc close'
        scr.addnstr(y0 + bh - 1, x0 + 1, hint, bw - 2, theme.REV | curses.A_DIM)
        curses.curs_set(0)
