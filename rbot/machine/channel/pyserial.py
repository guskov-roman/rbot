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

import os
import typing
import serial
import rbot.error

from . import channel

READ_CHUNK_SIZE = 4096

_AnyPath = typing.Union[str, os.PathLike]


class PyserialChannelIO(channel.ChannelIO):
    def __init__(self, port: _AnyPath, baudrate: int) -> None:
        self.serial = serial.Serial(os.fspath(port), baudrate=baudrate, exclusive=True)
        self.serial.timeout = 0

    def write(self, buf: bytes) -> int:
        if self.closed:
            raise channel.ChannelClosedException()

        rbot.log.debug(self, buf, True)
        self.serial.write(buf)
        return len(buf)

    def read(self, n: int, timeout: typing.Optional[float] = None) -> bytes:
        if self.closed:
            raise channel.ChannelClosedException()

        try:
            # Block for the first byte only
            self.serial.timeout = timeout
            first = self.serial.read(1)

            if first == b"":
                raise TimeoutError()

            assert len(first) == 1, f"Result is longer than expected ({first!r})!"
        finally:
            self.serial.timeout = 0

        remaining = b""
        if n > 1:
            # If there is more, read it now (non-blocking)
            remaining = self.serial.read(min(n, READ_CHUNK_SIZE) - 1)

        return rbot.log.debug(self, first + remaining)

    def close(self) -> None:
        if self.closed:
            raise channel.ChannelClosedException()

        self.serial.close()

    def fileno(self) -> int:
        return self.serial.fileno()

    @property
    def closed(self) -> bool:
        return not self.serial.is_open

    def update_pty(self, columns: int, lines: int) -> None:
        rbot.log.warning("Cannot update pty for pyserial connections")


class PyserialChannel(channel.Channel):
    def __init__(self, port: _AnyPath, baudrate: int) -> None:
        super().__init__(PyserialChannelIO(port, baudrate))
