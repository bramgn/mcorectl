"""Entry point: curses loop, startup and argument handling."""

from .common import *
from . import theme
from .app import App


async def ui(scr, app: App):
    curses.curs_set(1)
    theme.init_colors(app.theme)
    scr.nodelay(True)
    scr.keypad(True)
    while not app.quit:
        try:
            k = scr.get_wch()
        except curses.error:
            k = None
        if k is None:
            if app._status_expiry and time.monotonic() > app._status_expiry:
                app._status, app._status_expiry = '', None
                app.dirty = True
            if app.dirty:
                app.dirty = False
                app.draw(scr)
            await asyncio.sleep(0.03)
            continue
        if k == curses.KEY_RESIZE:
            app.dirty = True
            continue
        await app.handle_key(k)

async def run(scr, args):
    app = App(args)
    if app.auto_connect:
        app.start_auto_connect()
    async def autosave():
        while True:
            await asyncio.sleep(10)
            app.save_history()
    saver = asyncio.create_task(autosave())
    try:
        await ui(scr, app)
    finally:
        saver.cancel()
        app.save_history()
        await app.disconnect()

def main():
    ap = argparse.ArgumentParser(description='ncurses MeshCore chat client')
    ap.add_argument('--port', default=os.environ.get('MCORECHAT_PORT'))
    ap.add_argument('--ble', metavar='ADDRESS', help='connect over BLE instead of serial')
    args = ap.parse_args()
    saved = load_config()
    if not args.port and not args.ble:
        args.ble = saved.get('ble')          # remember last used target
    args.port = args.port or saved.get('port') or DEFAULT_PORT
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')   # ncurses waits 1000ms after Esc by default
    # keep library log output off the screen; F7 shows it
    root = logging.getLogger()
    root.handlers[:] = [LOG]
    root.setLevel(logging.INFO)

    def wrapped(scr):
        asyncio.run(run(scr, args))

    try:
        curses.wrapper(lambda scr: (curses.raw(), wrapped(scr)))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise SystemExit(f'mcorechat: {type(e).__name__}: {e}')
