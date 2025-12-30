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

import abc
import os
import contextlib
import typing

import rbot
import rbot.error
from rbot import machine  # noqa: F401
from .. import channel
from ..shell import linux
from . import connector

Self = typing.TypeVar("Self", bound="PyserialConnector")

_AnyPath = typing.Union[str, os.PathLike]


class PyserialConnector(connector.Connector):
    """
    Connect to a console connected to **localhost** (i.e. the host rbot is
    running on) using `pyserial`_.

    **Example**:

    .. code-block:: python

        from rbot_contrib.connector import pyserial

        class MyBoard(pyserial.PyserialConnector, board.Board):
            serial_port = "/dev/ttyUSB0"
            baudrate = 57600
    """

    @property
    @abc.abstractmethod
    def serial_port(self) -> _AnyPath:
        """
        Serial port to connect to.  Keep in mind that this path is **not** on
        the lab-host but on the localhost.
        """
        raise rbot.error.AbstractMethodError()

    baudrate = 115200
    """
    Baudrate of the serial line.
    """

    def __init__(self, host: typing.Optional[linux.LinuxShell] = None) -> None:
        self.host = host

    @classmethod
    @contextlib.contextmanager
    def from_context(
        cls: typing.Type[Self], context: "rbot.Context"
    ) -> typing.Iterator[Self]:
        with cls() as m:
            yield m

    def _connect(self) -> channel.Channel:
        return channel.PyserialChannel(self.serial_port, self.baudrate)

    def clone(self) -> typing.NoReturn:
        raise rbot.error.RbotException("Can't clone a (py)serial connection")
