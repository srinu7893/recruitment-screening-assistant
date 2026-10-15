#!/bin/sh
set -eu
# A fresh container must obtain signatures before opening the scan port.
freshclam --stdout
freshclam --daemon --stdout &
exec clamd --foreground=true --config-file=/etc/clamav/clamd.conf
