"""Colour themes and display attributes (module globals are rebound by init_colors)."""

import curses


# display attributes; init_colors() swaps in colours when the terminal has them
REV = curses.A_REVERSE                   # bars and popups
SEL = curses.A_REVERSE | curses.A_BOLD   # highlighted row
HEAD = curses.A_BOLD | curses.A_UNDERLINE
UNREAD = curses.A_BOLD
ME = curses.A_DIM
NOTE = curses.A_DIM
FAIL = curses.A_BOLD
GOOD_BAR = curses.A_BOLD                 # success / failure on bars and popups
BAD_BAR = curses.A_BOLD | curses.A_UNDERLINE
BAD_WORDS = ('fail', 'not sent', 'error', 'no reply', 'timed out', 'incomplete', 'unknown',
             'not connected', 'no response', 'no free', 'too long', 'must be', 'already exists',
             'usage', 'no repeater', 'ambiguous', 'no stored', 'empty reply')
GOOD_WORDS = ('reachable', 'saved', 'route discovered', 'created', 'removed')


PROBLEM_WORDS = BAD_WORDS + ('usage', 'no command', 'select a contact', 'not in the contact', 'read-only')


def is_problem(text: str) -> bool:
    t = text.lower()
    return any(x in t for x in PROBLEM_WORDS)


def result_attr(text: str, base: int, red: bool = True) -> int:
    """Green for successful results, red for failed ones (if `red`), else base."""
    t = text.lower()
    if any(x in t for x in BAD_WORDS):
        return BAD_BAR if red else base
    if any(x in t for x in GOOD_WORDS):
        return GOOD_BAR
    return base


C = {n: getattr(curses, 'COLOR_' + n.upper()) for n in
     ('black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white')}
C['default'] = -1
# per theme: (fg, bg) for bars/popups, selection, headers, unread, own messages, notes, failures
THEMES = {
    'blue': (('white', 'blue'), ('black', 'cyan'), ('cyan', 'default'), ('yellow', 'default'),
             ('green', 'default'), ('magenta', 'default'), ('red', 'default')),
    'green': (('black', 'green'), ('white', 'black'), ('green', 'default'), ('yellow', 'default'),
              ('green', 'default'), ('cyan', 'default'), ('red', 'default')),
    'amber': (('black', 'yellow'), ('yellow', 'black'), ('yellow', 'default'), ('white', 'default'),
              ('yellow', 'default'), ('magenta', 'default'), ('red', 'default')),
    'light': (('white', 'black'), ('white', 'blue'), ('blue', 'default'), ('red', 'default'),
              ('green', 'default'), ('magenta', 'default'), ('red', 'default')),
    'mono': None,
}


def init_colors(theme: str = 'blue'):
    global REV, SEL, HEAD, UNREAD, ME, NOTE, FAIL, GOOD_BAR, BAD_BAR
    pairs = THEMES.get(theme)
    if pairs is None or not curses.has_colors():
        REV, SEL, HEAD = curses.A_REVERSE, curses.A_REVERSE | curses.A_BOLD, curses.A_BOLD | curses.A_UNDERLINE
        UNREAD, ME, NOTE, FAIL = curses.A_BOLD, curses.A_DIM, curses.A_DIM, curses.A_BOLD
        GOOD_BAR, BAD_BAR = curses.A_BOLD, curses.A_BOLD | curses.A_UNDERLINE
        return
    curses.start_color()
    curses.use_default_colors()
    for n, (fg, bg) in enumerate(pairs, 1):
        curses.init_pair(n, C[fg], C[bg])
    REV = curses.color_pair(1)
    SEL = curses.color_pair(2) | curses.A_BOLD
    HEAD = curses.color_pair(3) | curses.A_BOLD
    UNREAD = curses.color_pair(4) | curses.A_BOLD
    ME = curses.color_pair(5)
    NOTE = curses.color_pair(6)
    FAIL = curses.color_pair(7) | curses.A_BOLD
    curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(9, curses.COLOR_WHITE, curses.COLOR_RED)
    GOOD_BAR = curses.color_pair(8)
    BAD_BAR = curses.color_pair(9) | curses.A_BOLD
