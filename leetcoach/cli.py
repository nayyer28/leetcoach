"""Backward-compatible CLI import path."""

from leetcoach.app.interface.cli import commands as _commands

cli = _commands.cli
_check_telegram_get_me = _commands._check_telegram_get_me
_mask_token = _commands._mask_token
request = _commands.request
subprocess = _commands.subprocess
