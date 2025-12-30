# rbot, System Development Automation Tool
# Copyright (C) 2025  Roman Guskov
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


from typing import Optional

import rbot.error

from . import channel


class NullChannelIO(channel.ChannelIO):
    def __init__(self) -> None:
        self._closed = False

    def write(self, buf: bytes) -> int:
        raise rbot.error.RbotException("Cannot write to a NULL channel")

    def read(self, n: int, timeout: Optional[float] = None) -> bytes:
        raise rbot.error.RbotException("Cannot read from a NULL channel")

    def close(self) -> None:
        self._closed = True

    def fileno(self) -> int:
        raise rbot.error.RbotException("NULL channel has no fileno")

    @property
    def closed(self) -> bool:
        return self._closed

    def update_pty(self, columns: int, lines: int) -> None:
        pass


class NullChannel(channel.Channel):
    def __init__(self) -> None:
        super().__init__(NullChannelIO())
