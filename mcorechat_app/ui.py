"""UiMixin for the mcorechat App."""

from .common import *
from . import theme, __version__


class UiMixin:
    async def handle_key(self, k):
        if k == '\x0c':                       # Ctrl-L: full repaint
            self.repaint = True
            self.dirty = True
            return
        if self.details is not None:
            self.dirty = True
            page = max(1, self.scr_h - 5)
            if k in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE,
                     curses.KEY_HOME, curses.KEY_END):
                self.details_scroll = {curses.KEY_UP: self.details_scroll - 1,
                                       curses.KEY_DOWN: self.details_scroll + 1,
                                       curses.KEY_PPAGE: self.details_scroll - page,
                                       curses.KEY_NPAGE: self.details_scroll + page,
                                       curses.KEY_HOME: 0, curses.KEY_END: 10 ** 6}[k]
                return
            self.details = None
            back, self.details_back = self.details_back, None
            if back and self.selected == back[0]:        # one step back: the menu the window came from
                self.cmenu_open, self.cmenu_sel = True, back[1]
            return
        if self.help_open:
            if k == curses.KEY_UP:
                self.help_scroll = max(0, self.help_scroll - 1)
            elif k == curses.KEY_DOWN:
                self.help_scroll += 1
            elif k == curses.KEY_PPAGE:
                self.help_scroll = max(0, self.help_scroll - 10)
            elif k == curses.KEY_NPAGE:
                self.help_scroll += 10
            else:
                self.help_open = False
            self.dirty = True
            return
        if self.confirm_quit:
            if k in ('y', 'Y', '\n'):
                self.quit = True
            elif k in ('n', 'N', '\x1b', curses.KEY_F10):
                self.confirm_quit = False
            self.dirty = True
            return
        if self.ask:
            await self.handle_ask_key(k)
            return
        if self.confirm_remove:
            if k in ('y', 'Y'):
                run, self.confirm_remove = self.confirm_remove['run'], None
                await run()
            elif k in ('n', 'N', '\x1b', '\n'):
                self.confirm_remove = None
            self.dirty = True
            return
        if self.search:
            self.handle_search_key(k)
            return
        if self.cmenu_open:
            await self.handle_cmenu_key(k)
            return
        if self.advert_menu_open:
            await self.handle_advert_key(k)
            return
        if k == curses.KEY_F10:
            self.confirm_quit = True
            self.dirty = True
            return
        if k == curses.KEY_F7 and not (self.picker_open or self.settings_open):
            self.open_contact_menu()
            self.dirty = True
            return
        if k == curses.KEY_F1:
            self.help_open, self.help_scroll = True, 0
            self.dirty = True
            return
        if k in (curses.KEY_F8, curses.KEY_F9):
            self.select(LOG_KEY if k == curses.KEY_F8 else RX_KEY)
            return
        if self.picker_open:
            await self.handle_picker_key(k)
            return
        if k == curses.KEY_F2 and not self.settings_open:
            self.settings_open = True
            self.dirty = True
            return
        if self.settings_open:
            await self.handle_settings_key(k)
            return
        if self.focus == 'side' and self.handle_side_key(k):
            return
        if self.focus == 'msgs' and self.handle_msg_focus_key(k):
            return
        if isinstance(k, str):
            o = ord(k) if len(k) == 1 else -1
            if k == '\n':
                text, self.buf, self.pos = self.buf.strip(), '', 0
                await self.submit(text)
            elif o in (CTRL_Q, CTRL_C):
                self.quit = True
            elif k == '\t':
                if self.buf.startswith('/') and ' ' not in self.buf:
                    self.complete()
                elif self.history.get(self.selected):
                    self.focus = 'msgs'
                    self.msg_sel = len(self.history[self.selected]) - 1
                else:
                    self.focus = 'side'
            elif k == '\x1b':
                self.focus = 'side'
            elif k in ('\x7f', '\b'):
                if self.pos:
                    self.buf = self.buf[:self.pos - 1] + self.buf[self.pos:]
                    self.pos -= 1
            elif o == 1:                       # ^A  home
                self.pos = 0
            elif o == 5:                       # ^E  end
                self.pos = len(self.buf)
            elif o == 2:                       # ^B  back
                self.pos = max(0, self.pos - 1)
            elif o == 6:                       # ^F  forward
                self.pos = min(len(self.buf), self.pos + 1)
            elif o == 4:                       # ^D  delete char
                self.buf = self.buf[:self.pos] + self.buf[self.pos + 1:]
            elif o == 21:                      # ^U  kill to start of line
                self.kill, self.buf, self.pos = self.buf[:self.pos], self.buf[self.pos:], 0
            elif o == 11:                      # ^K  kill to end of line
                self.kill, self.buf = self.buf[self.pos:], self.buf[:self.pos]
            elif o == 23:                      # ^W  kill previous word
                start = len(self.buf[:self.pos].rstrip())
                start = self.buf.rfind(' ', 0, start) + 1
                self.kill, self.buf, self.pos = (self.buf[start:self.pos],
                                                 self.buf[:start] + self.buf[self.pos:], start)
            elif o == 25:                      # ^Y  yank
                self.buf = self.buf[:self.pos] + self.kill + self.buf[self.pos:]
                self.pos += len(self.kill)
            elif o == 16:                      # ^P  previous conversation
                self.move(-1)
            elif o == 14:                      # ^N  next conversation
                self.move(1)
            elif k.isprintable():
                self.buf = self.buf[:self.pos] + k + self.buf[self.pos:]
                self.pos += 1
        elif k == curses.KEY_UP:
            self.move(-1)
        elif k == curses.KEY_DOWN:
            self.move(1)
        elif k == curses.KEY_PPAGE:
            self.scroll += 5
        elif k == curses.KEY_NPAGE:
            self.scroll = max(0, self.scroll - 5)
        elif k == curses.KEY_LEFT:
            self.pos = max(0, self.pos - 1)
        elif k == curses.KEY_RIGHT:
            self.pos = min(len(self.buf), self.pos + 1)
        elif k == curses.KEY_HOME:
            self.pos = 0
        elif k == curses.KEY_END:
            self.pos = len(self.buf)
        elif k == curses.KEY_BACKSPACE:
            if self.pos:
                self.buf = self.buf[:self.pos - 1] + self.buf[self.pos:]
                self.pos -= 1
        elif k == curses.KEY_DC:
            self.buf = self.buf[:self.pos] + self.buf[self.pos + 1:]
        elif k == curses.KEY_F3:
            await self.toggle_connection()
        self.dirty = True

    def handle_side_key(self, k) -> bool:
        """Keys while the list on the left has focus; returns False to fall through to the input."""
        if k in (curses.KEY_UP, '\x10'):
            self.move(-1)
        elif k in (curses.KEY_DOWN, '\x0e'):
            self.move(1)
        elif k == curses.KEY_PPAGE:
            self.scroll += 5
        elif k == curses.KEY_NPAGE:
            self.scroll = max(0, self.scroll - 5)
        elif k == '\n':
            self.open_contact_menu()
        elif k == '\t':
            self.focus = 'input'
        elif k == '\x1b':
            pass
        elif isinstance(k, str) and not (len(k) == 1 and ord(k) in (CTRL_Q, CTRL_C)):
            self.focus = 'input'              # typing from the list starts a message
            return False
        else:
            return False
        self.dirty = True
        return True

    def draw(self, scr):
        h, w = scr.getmaxyx()
        self.scr_h = h
        if self.repaint:
            scr.clear()
            self.repaint = False
        scr.erase()
        if h < 6 or w < SIDEBAR_W + 20:
            scr.addstr(0, 0, 'terminal too small'[:w - 1])
            scr.refresh()
            return
        sw = SIDEBAR_W
        mw = w - sw - 1
        body_h = h - 3                      # title row at 0, input + status at bottom

        # sidebar
        ents = self.entries()
        rows: list[tuple[str, tuple | None]] = []
        n_ch = len(self.channels)
        rows.append(('Channels', None))
        for k, n in ents[:n_ch]:
            rows.append((n, k))
        people = [(k, n) for k, n in ents[n_ch:-2] if not self.is_infra(k)]
        infra = [(k, n) for k, n in ents[n_ch:-2] if self.is_infra(k)]
        rows.append(('Contacts', None))
        rows += [(n, k) for k, n in people]
        if infra:
            rows.append(('Repeaters', None))
            rows += [(n, k) for k, n in infra]
        rows.append(('Console', None))
        for k, n in ents[-2:]:
            rows.append((n, k))
        sel_row = next((i for i, (_, k) in enumerate(rows) if k == self.selected), 0)
        top = max(0, min(sel_row - body_h // 2, len(rows) - body_h))
        for y, (label, key) in enumerate(rows[top:top + body_h]):
            if key is None:
                scr.addnstr(1 + y, 0, label, sw - 1, theme.HEAD)
                continue
            u = self.unread.get(key, 0)
            tail = f' {u}' if u else ''
            text = ' ' + label[:sw - 3 - len(tail)]
            text = text.ljust(sw - 1 - len(tail)) + tail
            attr = theme.SEL if key == self.selected else (
                theme.UNREAD if u else curses.A_NORMAL)
            scr.addnstr(1 + y, 0, text, sw - 1, attr)
        for y in range(1, h - 2):
            scr.addstr(y, sw, '│')

        # title
        si = (self.mc.self_info if self.mc else None) or {}
        title = f' mcorechat {__version__} — {si["name"]} ' if si.get('name') else f' mcorechat {__version__} '
        if self.mc and self.radio_bat:
            title += f'· bat {max(0, min(100, round((self.radio_bat - 3000) / 12)))}% '
        if self.selected:
            title += f'— {self.name_for(self.selected)} '
            if self.repeater_cli() == 'on':
                title += '(CLI) '
        scr.addnstr(0, 0, ' ' * w, w - 1, theme.REV)
        scr.addnstr(0, 0, title, w - 1, theme.REV)
        conn = self.connection_text()          # the title bar only ever shows the connection state
        room = w - 1 - len(title) - 2
        if room > 8:
            conn = conn if len(conn) <= room else conn[:room - 1] + '…'
            scr.addnstr(0, w - 1 - len(conn) - 1, conn, room, theme.REV)

        # messages
        lines = self.render_lines(mw)
        self.last_body_h = body_h
        if self.focus == 'msgs':
            self.msg_sel = max(0, min(self.msg_sel, len(self.history.get(self.selected, [])) - 1))
            idx = [i for i, l in enumerate(lines) if l[2] == self.msg_sel]
            if idx:                          # scroll so the highlighted message is visible
                end_now = len(lines) - self.scroll
                if idx[-1] >= end_now:
                    self.scroll = len(lines) - idx[-1] - 1
                elif idx[0] < end_now - body_h:
                    self.scroll = max(0, len(lines) - idx[0] - body_h)
        self.scroll = min(self.scroll, max(0, len(lines) - body_h))
        end = len(lines) - self.scroll
        for y, (text, attr, n) in enumerate(lines[max(0, end - body_h):end]):
            if self.focus == 'msgs' and n == self.msg_sel:
                attr = theme.SEL
            scr.addnstr(1 + y, sw + 1, text, mw, attr)
        if self.scroll:
            scr.addnstr(body_h, sw + 1, f'-- {self.scroll} lines up (PgDn) --', mw, curses.A_DIM)

        # input + status
        cli = self.repeater_cli()
        prompt = f'{self.name_for(self.selected)[:14]}# ' if cli == 'on' else '> '
        vis = w - len(prompt) - 1
        start = max(0, self.pos - vis + 1)
        if self.focus == 'side' and not self.buf:
            scr.addnstr(h - 2, 0, 'Enter: menu · Tab: write a message · type to start one', w - 1, curses.A_DIM)
        else:
            scr.addnstr(h - 2, 0, prompt + self.buf[start:start + vis], w - 1)
            if not self.buf and cli:
                hint = ('commands go to the repeater: ver, clock, advert, ...' if cli == 'on'
                        else 'not logged in: Esc, Enter, then "CLI" to manage this repeater')
                scr.addnstr(h - 2, len(prompt), hint, max(0, w - 1 - len(prompt)), curses.A_DIM)
        keys = [('F1', 'Help'), ('F2', 'Options'),
                ('F3', 'Disconnect' if self.mc else 'Connect'),
                ('F7', 'Menu'), ('F8', 'Log'), ('F9', 'RX log'), ('F10', 'Quit')]
        status = ' ' + '  '.join(f'{k} {v}' for k, v in keys)
        scr.addnstr(h - 1, 0, status.ljust(w), w - 1, theme.REV)
        scr.move(h - 2, min(w - 1, len(prompt) + self.pos - start))
        curses.curs_set(1 if self.focus == 'input' else 0)
        if self.settings_open:
            self.draw_settings(scr, h, w)
        if self.picker_open:
            self.draw_picker(scr, h, w)
        if self.help_open:
            self.draw_help(scr, h, w)
        if self.details is not None:
            self.draw_details(scr, h, w)
        if self.search:
            self.draw_search(scr, h, w)
        if self.cmenu_open:
            self.draw_cmenu(scr, h, w)
        if self.advert_menu_open:
            self.draw_advert_menu(scr, h, w)
        if self.ask:
            self.draw_ask(scr, h, w)
        if self.confirm_remove:
            msg = f' {self.confirm_remove["label"]}?  [y] yes  [n/Esc] no '
            y0, x0 = h // 2, max(0, (w - len(msg)) // 2)
            scr.addnstr(y0, x0, msg, w - 1 - x0, theme.REV | curses.A_BOLD)
            curses.curs_set(0)
        if self.confirm_quit:
            msg = ' Quit mcorechat?  [y/Enter] yes  [n/Esc] no '
            y0, x0 = h // 2, max(0, (w - len(msg)) // 2)
            scr.addnstr(y0, x0, msg, w - 1 - x0, theme.REV | curses.A_BOLD)
            curses.curs_set(0)
        scr.refresh()
