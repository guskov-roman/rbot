# rbot, Automation Tool
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

import getpass
import paramiko
import socket
import typing
import shutil

import rbot.exceptions

from rbot.channel import channel, common

# compatibility exceptions aliases
ChannelClosedException = rbot.exceptions.ChannelClosedException
InvalidRetcodeException = rbot.exceptions.InvalidRetcodeException

RBOT_PROMPT = b"RBOT-TESTVC9QK$ "


class SSHChannelIO(channel.ChannelIO):
    __slots__ = ("ch",)

    def __init__(self, channel: paramiko.Channel):
        self.ch = channel
        self.ch.get_pty("xterm-256color", 80, 25, 1024, 1024)
        self.ch.invoke_shell()
        self.ch.settimeout(0.0)

    def write(self, buf: bytes) -> int:
        if self.closed:
            raise ChannelClosedException

        bytes_written = self.ch.send(buf)
        if bytes_written == 0:
            raise ChannelClosedException
        return bytes_written

    def read(self, n: int, timeout: typing.Optional[float] = None) -> bytes:
        self.ch.settimeout(timeout)
        try:
            read_buf = self.ch.recv(n)
            return read_buf
        except socket.timeout:
            raise TimeoutError()
        finally:
            self.ch.settimeout(0.0)

    def close(self) -> None:
        if self.closed:
            raise ChannelClosedException

        self.ch.close()

    def fileno(self) -> int:
        return self.ch.fileno()

    @property
    def closed(self) -> bool:
        if self.ch:
            return self.ch.exit_status_ready()
        return True

    def update_pty(self, columns: int, lines: int) -> None:
        self.ch.resize_pty(columns, lines, 1024, 1024)


class SSHChannel(common.PosixChannel):
    __slots__ = "_client"

    @property
    def hostname(self) -> str:
        return self._hostname

    @hostname.setter
    def hostname(self, name: str) -> None:
        if name is not None:
            self._hostname = name

    @property
    def username(self) -> str:
        if self._username is None:
            return getpass.getuser()

        return self._username

    @username.setter
    def username(self, user: str) -> None:
        if user is not None:
            self._username = user

    @property
    def password(self) -> str:
        return self._password

    @password.setter
    def password(self, password: str) -> None:
        if password is not None:
            self._password = password

    @property
    def port(self) -> int:
        if self._port is None:
            return 22
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        if port is not None:
            self._port = port

    @property
    def key_file(self) -> str:
        return self._key_filename

    @key_file.setter
    def key_file(self, key_file: str) -> None:
        if key_file is not None:
            self._key_filename = key_file

    @property
    def ignore_hostkey(self) -> bool:
        return self._ignore_hostkey

    @ignore_hostkey.setter
    def ignore_hostkey(self, ignore_hostkey: bool) -> None:
        if ignore_hostkey is not None:
            self._ignore_hostkey = ignore_hostkey

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.username}@{self.hostname}:{self.port}>"
        )

    def __init__(
        self,
        hostname=None,
        username=None,
        password=None,
        port=None,
        key_filename=None,
        ignore_hostkey=False,
    ) -> None:

        self.name = "ssh"
        self._hostname = hostname
        self._username = username
        self._password = password
        self._port = port
        self._key_filename = key_filename
        self._ignore_hostkey = ignore_hostkey

        self._client: typing.Optional[paramiko.SSHClient] = None

    def open(self, *args, **kwargs) -> None:

        # TODO Read config file

        if self._client is None:
            self._client = paramiko.SSHClient()

            if self._ignore_hostkey:
                self._client.set_missing_host_key_policy(
                    paramiko.client.AutoAddPolicy()
                )
            else:
                self._client.load_system_host_keys()

            print(f"Logging in on {self.username}@{self.hostname}:{self._port} ...")

            self._client.connect(
                self.hostname,
                username=self.username,
                port=self.port,
                password=self.password,
                key_filename=self.key_file,
            )

            super().__init__(
                SSHChannelIO(channel=self._client.get_transport().open_session())
            )

            self._init_shell()

    def _init_shell(self):

        self._write_blacklist = [
            0x03,  # ETX  | End of Text / Interrupt
            0x04,  # EOT  | End of Transmission
            0x11,  # DC1  | Device Control One (XON)
            0x12,  # DC2  | Device Control Two
            0x13,  # DC3  | Device Control Three (XOFF)
            0x14,  # DC4  | Device Control Four
            0x15,  # NAK  | Negative Acknowledge
            0x16,  # SYN  | Synchronous Idle
            0x17,  # ETB  | End of Transmission Block
            0x1A,  # SUB  | Substitute / Suspend Process
            0x1C,  # FS   | File Separator
            0x7F,  # DEL  | Delete
        ]

        self.send("/bin/bash --norc --noprofile --noediting -i\r", read_back=False)

        self.sendline(
            b"PROMPT_COMMAND=''; PS1='"
            + RBOT_PROMPT[:6]
            + b"''"
            + RBOT_PROMPT[6:]
            + b"'",
            read_back=False,
        )
        self.prompt = RBOT_PROMPT

        self.read_until_prompt()
        self.sendline("unset HISTFILE")
        self.read_until_prompt()

        # # Disable line editing
        self.sendline("set +o emacs; set +o vi")
        self.read_until_prompt()

        # # Set secondary prompt to ""
        self.sendline("PS2=''")
        self.read_until_prompt()

        self.sendline("histchars=''")
        self.read_until_prompt()

        # # Set terminal size
        termsize = shutil.get_terminal_size()
        self.sendline(f"stty cols {max(80, termsize.columns - 48)}")
        self.read_until_prompt()
        self.sendline(f"stty rows {termsize.lines}")
        self.read_until_prompt()

    def interactive(self):
        super().interactive(f"{self.username}@{self.hostname}")
