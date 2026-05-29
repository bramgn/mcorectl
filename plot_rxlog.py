#!/usr/bin/env python3
"""Plot RSSI/SNR over time from a mcorectl rxlog CSV file.

Usage:
    python3 plot_rxlog.py lemvig.csv
"""

import sys
import csv
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

if len(sys.argv) < 2:
    print(f'Usage: {sys.argv[0]} <csvfile>')
    sys.exit(1)

timestamps, rssi_vals, snr_vals, nodes = [], [], [], []

with open(sys.argv[1]) as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            timestamps.append(datetime.fromisoformat(row['timestamp']))
            rssi_vals.append(float(row['rssi']))
            snr_vals.append(float(row['snr']))
            nodes.append(row.get('node', ''))
        except (ValueError, KeyError):
            continue

if not timestamps:
    print('No data found.')
    sys.exit(1)

node_label = nodes[0] if nodes[0] else 'unknown'
print(f'{len(timestamps)} data points for {node_label!r}')

fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(12, 6))
fig.suptitle(f'Link quality — {node_label}')

ax1.plot(timestamps, rssi_vals, marker='o', color='steelblue', linewidth=1)
ax1.set_ylabel('RSSI (dBm)')
ax1.grid(True, alpha=0.3)

ax2.plot(timestamps, snr_vals, marker='o', color='darkorange', linewidth=1)
ax2.set_ylabel('SNR (dB)')
ax2.grid(True, alpha=0.3)

ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
fig.autofmt_xdate()

plt.tight_layout()
plt.savefig('rxlog_plot.png', dpi=150)
print('Saved: rxlog_plot.png')
plt.show()
