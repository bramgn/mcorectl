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
    'light': (('white', 'black'), ('white', 'blue'), ('blue', 'default'), ('default', 'default'),
              ('green', 'default'), ('magenta', 'default'), ('red', 'default')),
    # 256-colour themes (ints are xterm palette indexes; terminals with fewer colours get the nearest basic colour)
    'vampire':   ((253, 61), (234, 212), (141, 'default'), (228, 'default'), (84, 'default'), (117, 'default'), (203, 'default')),
    'fjord':     ((254, 60), (236, 110), (110, 'default'), (222, 'default'), (108, 'default'), (139, 'default'), (167, 'default')),
    'sundial':   ((230, 23), (234, 136), (37, 'default'), (136, 'default'), (100, 'default'), (162, 'default'), (160, 'default')),
    'harvest':   ((223, 237), (235, 172), (172, 'default'), (214, 'default'), (142, 'default'), (132, 'default'), (167, 'default')),
    'shibuya':   ((189, 60), (234, 111), (111, 'default'), (215, 'default'), (149, 'default'), (141, 'default'), (204, 'default')),
    'synthwave': ((231, 54), (234, 207), (207, 'default'), (51, 'default'), (51, 'default'), (213, 'default'), (203, 'default')),
    'deepsea':   ((195, 24), (233, 80), (80, 'default'), (221, 'default'), (79, 'default'), (110, 'default'), (209, 'default')),
    'rosewater': ((224, 96), (235, 217), (183, 'default'), (222, 'default'), (109, 'default'), (175, 'default'), (204, 'default')),
    'mossy':     ((194, 22), (233, 107), (107, 'default'), (186, 'default'), (150, 'default'), (180, 'default'), (167, 'default')),
    'parchment': ((236, 223), (255, 130), (94, 'default'), ('default', 'default'), (64, 'default'), (125, 'default'), (124, 'default')),
    'mono': None,
}


def col(c) -> int:
    """A colour spec: basic name, 'default', or a 256-colour index (nearest basic colour on small terminals)."""
    if isinstance(c, str):
        return C[c]
    if curses.COLORS >= 256:
        return c
    if c < 16:
        r, g, b = (c & 1) * 255, (c >> 1 & 1) * 255, (c >> 2 & 1) * 255
    elif c < 232:
        r, g, b = ((c - 16) // 36) * 51, ((c - 16) // 6 % 6) * 51, ((c - 16) % 6) * 51
    else:
        r = g = b = 8 + (c - 232) * 10
    return (r >= 128) | (g >= 128) << 1 | (b >= 128) << 2   # curses colour numbers are bit-ordered r,g,b


DESCRIPTIONS = {
    'blue': 'classic white-on-blue bars', 'green': 'green phosphor terminal', 'amber': 'amber CRT',
    'light': 'for light terminals', 'mono': 'no colour, bold and reverse only',
    'vampire': 'purple and pink on dark (Dracula-ish)', 'fjord': 'cold blues and soft frost (Nord-ish)',
    'sundial': 'teal and mustard (Solarized-ish)', 'harvest': 'warm retro earth tones (Gruvbox-ish)',
    'shibuya': 'rainy neon night (Tokyo Night-ish)', 'synthwave': 'magenta and cyan 80s grid',
    'deepsea': 'dark teal with coral accents', 'rosewater': 'dusky rose and pine (Rose Pine-ish)',
    'mossy': 'forest greens and bark', 'parchment': 'warm paper for light terminals',
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
        curses.init_pair(n, col(fg), col(bg))
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
