"""Shared imports, constants and small helpers."""

import argparse
import asyncio
import curses
import locale
import os
import collections
import glob
import json
import logging
import math
import textwrap
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from serial.tools import list_ports
from meshcore import MeshCore, SerialConnection, BLEConnection
from meshcore.events import EventType

DEFAULT_PORT = '/dev/ttyUSB0'
CONFIG_FILE = os.path.expanduser('~/.config/mcorechat/config.json')
HISTORY_FILE = os.path.expanduser('~/.config/mcorechat/history.json')
RX_KEY = ('r', 0)           # 'Radio': received packets as a pseudo-conversation
LOG_KEY = ('l', 0)          # 'Log': status messages and library log lines
MAX_RETRIES = 5
HISTORY_KEEP = 500          # messages kept per conversation
SIDEBAR_W = 24
MAX_CHANNELS = 8
BLE_UART_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
NODE_TYPES = {1: 'client', 2: 'repeater', 3: 'room'}
CTRL_Q, CTRL_C = 17, 3
LOG_LINES = 1000


def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def describe_error(payload: dict) -> str:
    """Human-readable reason for a radio ERROR event (payload may be empty)."""
    if payload.get('code_string'):
        return payload['code_string']
    if payload.get('reason'):
        return payload['reason']
    if payload.get('error'):
        return str(payload['error'])
    if 'error_code' in payload:
        return f'error code {payload["error_code"]}'
    return 'radio rejected the command (no error code)'


class LogBuffer(logging.Handler):
    """Collects log records (ours and the meshcore library's); the App shows them as the Log conversation."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.records: collections.deque = collections.deque(maxlen=LOG_LINES)   # kept until a sink attaches
        self.sink = None

    def emit(self, record):
        try:
            if self.sink:
                self.sink(record)
            else:
                self.records.append(record)
        except Exception:
            pass


LOG = LogBuffer()
log = logging.getLogger('mcorechat')


@dataclass
class Msg:
    ts: int
    who: str
    text: str
    mine: bool = False
    status: str = ''   # '' | 'sent' | 'acked' | 'failed'
    recv: int = 0                          # local time we saw it
    info: dict = field(default_factory=dict)   # raw radio fields for the details view


def hhmm(ts: int) -> str:
    return datetime.fromtimestamp(ts or datetime.now().timestamp()).strftime('%H:%M')
