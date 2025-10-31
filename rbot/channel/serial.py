# rbot, Automation Tool
# Copyright (C) 2025 Roman Guskov
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
import pathlib
import subprocess
import serial

import rbot.exceptions
from rbot.channel import channel

ChannelClosedException = rbot.exceptions.ChannelClosedException
InvalidRetcodeException = rbot.exceptions.InvalidRetcodeException

READ_CHUNK_SIZE = 4096

_AnyPath = typing.Union[str, os.PathLike]


class SerialChannelIO(channel.ChannelIO):

    def __init__(self, port: _AnyPath, baudrate: int):
        try:
            self.ch = serial.Serial(os.fspath(port), baudrate=baudrate, exclusive=True)
            self.ch.timeout = 0
        except Exception as ex:
            # TODO Add exceptions ChanelOpenExceptions
            raise RuntimeError(f"{ex}")

    def write(self, buf: bytes) -> int:
        if self.closed:
            raise ChannelClosedException

        self.ch.write(buf)
        return len(buf)

    def read(self, n: int, timeout: typing.Optional[float] = None) -> bytes:
        if self.closed:
            raise ChannelClosedException

        try:
            # Block for the first byte only
            self.ch.timeout = 0.1 if timeout is None else timeout
            first = self.ch.read(1)

            if first == b"":
                raise TimeoutError()

            assert len(first) == 1, f"Result is longer than expected ({first!r})!"
        finally:
            self.ch.timeout = 0

        remaining = b""
        if n > 1:
            # self.ch.timeout = 1
            # If there is more, read it now (non-blocking)
            remaining = self.ch.read(min(n, READ_CHUNK_SIZE) - 1)

        return first + remaining

    def close(self) -> None:
        if self.closed:
            raise ChannelClosedException

        self.ch.close()

    def fileno(self) -> int:
        return self.ch.fileno()

    @property
    def closed(self) -> bool:
        return not self.ch.is_open

    def update_pty(self, columns: int, lines: int) -> None:
        print("Cannot update pty for pyserial connections")


class SerialChannel(channel.Channel):

    @property
    def port(self) -> _AnyPath:
        return self._port

    @port.setter
    def port(self, port) -> None:
        self._port = port

    @property
    def baudrate(self) -> int:
        return self._baudrate

    @baudrate.setter
    def baudrate(self, baudrate):
        try:
            self._baudrate = baudrate if isinstance(baudrate, int) else int(baudrate)
        except ValueError:
            raise InvalidRetcodeException(baudrate) from None

    def __init__(self, port: _AnyPath, baudrate: int = 115200) -> None:
        self.name = f"serial@{port}"
        self._port = port
        self._baudrate = baudrate

    def open(self, *args, **kwargs) -> None:
        super().__init__(SerialChannelIO(self.port, self.baudrate))

    def xmodem_upload(self, file: typing.Union[str, pathlib.Path], callback=None):
        cmd = f"sx {file} < {self._port} > {self._port}"
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
        total_size = None
        send_size = None
        if callable(callback):
            while True:
                out = proc.stdout.readline()
                err = proc.stderr.readline()
                callable(out, err)
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

        return proc.wait()       
