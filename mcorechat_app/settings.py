"""SettingsMixin for the mcorechat App."""

from .common import *
from . import theme


class SettingsMixin:
    SETTINGS = ('port', 'autoconnect', 'name', 'tx_power', 'advert', 'auto_add', 'repeaters', 'retries', 'theme')

    def setting_rows(self) -> list[tuple[str, str]]:
        si = (self.mc.self_info if self.mc else None) or {}
        onoff = lambda b: 'on' if b else 'off'
        dash = lambda k: str(si[k]) if k in si else '-'
        return [
            ('BLE address' if self.args.ble else 'Serial port', self.target()),
            ('Connect on startup', onoff(self.auto_connect)),
            ('Device name', dash('name')),
            ('TX power (dBm)', dash('tx_power')),
            ('Send advert', 'zero hop / flood...'),
            ('Auto add discovered contacts',
             onoff(not si['manual_add_contacts']) if 'manual_add_contacts' in si else '-'),
            ('Show repeaters in list', onoff(self.show_repeaters)),
            ('Send retries', str(self.retries)),
            ('Colour theme', self.theme),
        ]

    async def apply_setting(self, which: str, text: str | None = None):
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
            self.theme = names[(names.index(self.theme) + 1) % len(names)]
            theme.init_colors(self.theme)
            self.save_config()
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
        elif k in ('\n', ' '):
            if which in ('port', 'name', 'tx_power'):
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
            'Enter change · Esc close'
        scr.addnstr(y0 + bh - 1, x0 + 1, hint, bw - 2, theme.REV | curses.A_DIM)
        curses.curs_set(0)
