"""CommandsMixin for the mcorechat App."""

from .common import *
from . import theme


class CommandsMixin:
    COMMAND_NAMES = ('advert', 'channel', 'connect', 'contact', 'disconnect', 'help', 'log', 'quit',
                     'reload', 'repeaters', 'radio', 'search', 'settings', 'trace')

    def complete(self):
        """Tab completion for /commands in the input line."""
        if not self.buf.startswith('/') or ' ' in self.buf or self.buf.startswith('//'):
            return
        cyc = getattr(self, '_tab', None)
        if cyc and self.buf == cyc[2]:                 # repeated Tab: next match
            hits, i = cyc[0], (cyc[1] + 1) % len(cyc[0])
        else:
            word = self.buf[1:].lower()
            hits, i = [c for c in self.COMMAND_NAMES if c.startswith(word)], -1
            if not hits:
                self.status = f'no command matches /{word}'
                return
            common = os.path.commonprefix(hits)
            if len(hits) > 1 and common == word:       # nothing more to add: start cycling
                i = 0
            else:
                self.buf = '/' + common
        if i >= 0:
            self.buf = '/' + hits[i]
        self.pos = len(self.buf)
        self._tab = (hits, i, self.buf) if len(hits) > 1 else None
        if len(hits) > 1:
            self.status = 'matches: ' + '  '.join('/' + c for c in hits)

    async def submit(self, text: str):
        if not text:
            return
        if not text.startswith('/') or text.startswith('//'):
            await self.send(text[1:] if text.startswith('//') else text)
            return
        name, _, arg = text[1:].partition(' ')
        name = name.lower()
        if name in ('contact', 'ct'):
            self.open_contact_menu()
            self.dirty = True
            return
        if name in ('a', 'advert'):
            kinds = {'': None, 'zero': False, 'zerohop': False, '0': False, 'flood': True}
            if arg.strip().lower() not in kinds:
                self.status = 'usage: /advert [zero|flood]'
            else:
                await self.advert(kinds[arg.strip().lower()])
            self.dirty = True
            return
        if name in ('f', 'find', 'search'):
            self.do_search(arg.strip())
            self.dirty = True
            return
        if name in ('t', 'trace'):
            await self.trace_command(arg)
            self.dirty = True
            return
        if name in ('ch', 'channel'):
            await self.create_channel(arg.strip())
            self.dirty = True
            return
        cmds = {
            ('q', 'quit', 'exit'): lambda: setattr(self, 'quit', True),
            ('c', 'connect'): self.pick_device,
            ('d', 'disconnect'): self.disconnect,
            ('r', 'reload'): self.reload,
            ('s', 'settings'): lambda: setattr(self, 'settings_open', True),
            ('l', 'log', 'console'): lambda: self.select(LOG_KEY),
            ('radio', 'rx', 'rxlog'): lambda: self.select(RX_KEY),
            ('repeaters',): lambda: setattr(self, 'show_repeaters', not self.show_repeaters),
            ('h', 'help', '?'): self.help,
        }
        for names, fn in cmds.items():
            if name in names:
                r = fn()
                if asyncio.iscoroutine(r):
                    await r
                self.dirty = True
                return
        self.status = f'unknown command /{name} (try /help)'

    HELP = (
        ('Keys', ''),
        ('Up / Down', 'select channel / contact'),
        ('PgUp / PgDn', 'scroll history'),
        ('Enter', 'send message; empty line on a contact = contact menu'),
        ('Tab', 'focus messages: Up/Down, Enter = details, r = resend failed'),
        ('F1', 'this help'),
        ('F2', 'settings'),
        ('F3', 'choose device and connect / disconnect'),
        ('F4', 'send advert (zero hop / flood)'),
        ('F5', 'reload contacts and channels'),
        ('F6', 'show / hide repeaters'),
        ('F7', 'Log: status messages (lights up on problems)'),
        ('F9', 'Radio: every packet heard (Tab: select, Enter = details)'),
        ('F8', 'contact menu: details, ping, trace, path, remove'),
        ('F10', 'quit (asks to confirm)'),
        ('^Q, ^C', 'quit immediately'),
        ('^A ^E', 'start / end of line'),
        ('^B ^F', 'cursor left / right'),
        ('^U ^K ^W', 'kill to start / end / previous word'),
        ('^Y ^D', 'yank / delete char'),
        ('^P ^N', 'previous / next conversation'),
        ('', ''),
        ('Commands', ''),
        ('Tab (after /)', 'complete a /command'),
        ('/help  /h  /?', 'this help'),
        ('/quit  /q', 'quit immediately'),
        ('/channel <name> [key]', 'create / join a channel (#name = public)'),
        ('/contact', 'contact menu (same as F8)'),
        ('/connect  /c', 'choose device and connect'),
        ('/disconnect  /d', 'disconnect from the radio'),
        ('/advert  /a', 'advert menu, or /advert zero|flood'),
        ('/log  /console', 'show the Log (F7)'),
        ('/radio  /rxlog', 'show the Radio packet list (F9)'),
        ('/search  /f', 'search all messages: /search <text>'),
        ('/trace  /t', 'trace hops: /trace 78,64,78 or repeater names'),
        ('/reload  /r', 'reload contacts and channels'),
        ('/settings  /s', 'settings'),
        ('/repeaters', 'show / hide repeaters'),
        ('//text', 'send a message starting with /'),
    )

    def help(self):
        self.help_open, self.help_scroll = True, 0

    def draw_help(self, scr, h, w):
        bw = min(w - 2, 72)
        room = max(3, h - 4)
        self.help_scroll = min(self.help_scroll, max(0, len(self.HELP) - room))
        rows = self.HELP[self.help_scroll:self.help_scroll + room]
        bh = len(rows) + 3
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for y in range(bh):
            scr.addstr(y0 + y, x0, ' ' * bw, theme.REV)
        scr.addnstr(y0, x0 + 1, 'Help', bw - 2, theme.REV | curses.A_BOLD)
        for i, (a, b) in enumerate(rows):
            if a and not b:
                scr.addnstr(y0 + 1 + i, x0 + 1, a, bw - 2, theme.REV | curses.A_UNDERLINE)
            else:
                scr.addnstr(y0 + 1 + i, x0 + 1, f'{a:<24}{b}', bw - 2, theme.REV)
        scr.addnstr(y0 + bh - 1, x0 + 1, 'Up/Down scroll · any other key closes' if len(self.HELP) > room
                    else 'press any key to close', bw - 2, theme.REV | curses.A_DIM)
        curses.curs_set(0)
