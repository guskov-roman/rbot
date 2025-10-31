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

import fcntl
import os
import pty
import select
import struct
import shutil
import subprocess
import termios
import time
import typing

import rbot.exceptions

from rbot.channel import channel, common


RBOT_PROMPT = b"RBOT-TESTVC9QK$ "


class ShellChannelIO(channel.ChannelIO):
    __slots__ = ("pty_master", "pty_slave", "p")

    MIN_READ_WAIT = 0.3
    _debug_callback: typing.Union[typing.Callable, None] = None

    def __init__(self):
        self.pty_master, self.pty_slave = pty.openpty()
        self.p = subprocess.Popen(
            ["bash", "--norc", "--noprofile", "--noediting", "-i"],
            stdin=self.pty_slave,
            stdout=self.pty_slave,
            stderr=self.pty_slave,
            start_new_session=True,
        )

        flags = fcntl.fcntl(self.pty_master, fcntl.F_GETFL)
        flags = flags | os.O_NONBLOCK
        fcntl.fcntl(self.pty_master, fcntl.F_SETFL, flags)

    def write(self, buf: bytes) -> int:
        if self.closed:
            raise rbot.exceptions.ChannelClosedException

        _, w, _ = select.select([], [self.pty_master], [], 10.0)
        if self.pty_master not in w:
            raise TimeoutError("write timeout exceeded")

        bytes_written = os.write(self.pty_master, buf)

        if bytes_written == 0:
            raise rbot.exceptions.ChannelClosedException
        return bytes_written

    def read(self, n: int, timeout: typing.Optional[float] = None) -> bytes:
        if not self.closed:
            # If the process is still running, wait for one byte or the timeout
            # to arrive.  We run select(2) in a loop to periodically (each
            # second) monitor whether the subprocess is still running.

            end_time = None if timeout is None else time.monotonic() + timeout
            while True:
                if end_time is None:
                    select_timeout = self.MIN_READ_WAIT
                else:
                    select_timeout = min(
                        self.MIN_READ_WAIT, end_time - time.monotonic()
                    )
                    if select_timeout <= 0:
                        raise TimeoutError()

                r, _, _ = select.select([self.pty_master], [], [], select_timeout)

                if self.pty_master in r:
                    # There is something to read, proceed to reading it.
                    break
                elif self.closed:
                    # Nothing to read and channel is closed.  We're done for good.
                    raise rbot.exceptions.ChannelClosedException

                # Loop back around and try again until timeout expires.

        try:
            read_buf = os.read(self.pty_master, n)
            if callable(self._debug_callback):
                self._debug_callback(read_buf)
            return read_buf
        except (BlockingIOError, OSError):
            raise rbot.exceptions.ChannelClosedException

    def close(self) -> None:
        if self.closed:
            raise rbot.exceptions.ChannelClosedException

        sid = os.getsid(self.p.pid)
        self.p.terminate()
        os.close(self.pty_slave)
        os.close(self.pty_master)
        try:
            self.p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.communicate()

        # Wait for all processes in the session to end.  Most of the time this
        # will return immediately, but in some cases (eg. a serial session with
        # picocom) we have to wait a bit until we can continue.
        wait_total = 0.0
        for t in range(10):
            if (
                subprocess.call(
                    ["ps", "-s", str(sid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                != 0
            ):
                break

            wait_time = 2**t / 100

            if t >= 7:
                offending = (
                    subprocess.run(
                        ["ps", "-s", str(sid), "ho", "args"],
                        stdout=subprocess.PIPE,
                        encoding="utf-8",
                    )
                    .stdout.strip()
                    .split("\n")
                )
                # TODO add log warning
                offending_str = "\n".join(f" - {args!r}" for args in offending)

                print(
                    f"""\
Some subprocesses have not stopped after {wait_total:.1f} s:

{offending_str}

You should probably consider to explicitly terminate the offending processes in
your connector configuration.

Waiting for {wait_time:.1f} more seconds..."""
                )

            time.sleep(wait_time)
            wait_total += wait_time
        else:
            raise rbot.exceptions.RbotException("some subprocess(es) did not stop")

    def fileno(self) -> int:
        return self.pty_master

    @property
    def closed(self) -> bool:
        self.p.poll()
        return self.p.returncode is not None

    def update_pty(self, columns: int, lines: int) -> None:
        s = struct.pack("HHHH", lines, columns, 0, 0)
        fcntl.ioctl(self.pty_master, termios.TIOCSWINSZ, s, False)


class ShellChannel(common.PosixChannel):

    @property
    def debug(self):
        return self._c._debug_callback

    @debug.setter
    def debug(self, func):
        self._c._debug_callback = func

    def __init__(self) -> None:
        super().__init__(ShellChannelIO())

        self.name = "shell"

        # Set a blacklist of control characters.  These characters are
        # known to mess up the state of the shell.  They are:
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

        common.wait_for_shell(self)

        # Set prompt to a known string
        #
        # The prompt is mangled in a way which will be unfolded by the
        # shell.  This will ensure rbot won't accidentally read the prompt
        # back early if the connection is slow.
        self.sendline(
            b"PROMPT_COMMAND=''; PS1='"
            + RBOT_PROMPT[:6]
            + b"''"
            + RBOT_PROMPT[6:]
            + b"'",
        )
        self.prompt = RBOT_PROMPT
        self.read_until_prompt()

        # Disable history
        self.sendline("unset HISTFILE")
        self.read_until_prompt()

        # Disable line editing
        self.sendline("set +o emacs; set +o vi")
        self.read_until_prompt()

        # Set secondary prompt to ""
        self.sendline("PS2=''")
        self.read_until_prompt()

        # Disable history expansion because it is not always affected by
        # quoting rules and thus can mess with parameter values.  For
        # example, m.exec0("echo", "\n^") triggers the 'quick substitution'
        # feature and will return "\n!!:s^\n" instead of the expected
        # "\n^\n".  As it is not really useful for rbot tests anyway,
        # disable all history expansion 'magic characters' entirely.
        self.sendline("histchars=''")
        self.read_until_prompt()

        # Set terminal size
        termsize = shutil.get_terminal_size()
        self.sendline(f"stty cols {max(80, termsize.columns - 48)}")
        self.read_until_prompt()
        self.sendline(f"stty rows {termsize.lines}")
        self.read_until_prompt()

        # Do a sanity check to assert that shell interaction is working
        # exactly as expected
        common.shell_sanity_check(self)

    def open_channel(self, *args: typing.Union[str, bytes]) -> channel.Channel:
        cmd = common.escape(*args)

        # Disable the interrupt key in the outer shell
        self.sendline("stty -isig", read_back=True)
        self.read_until_prompt()

        self.sendline(cmd + "; exit", read_back=True)

        return self.take()
