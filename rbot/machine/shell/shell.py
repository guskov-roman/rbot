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
import contextlib
import typing

import rbot
import rbot.error
from .. import machine, channel

SearchString = channel.channel.SearchString
ConvenientSearchString = channel.channel.ConvenientSearchString


class Shell(machine.Machine):

    @abc.abstractmethod
    def _init_shell(self) -> typing.ContextManager:
        """
        Initialize this shell.

        An implementation of this method should return a context manager that,
        when entered, waits for the shell to appear on the channel and sets up
        any necessary options.  This might include deactivating line-editing,
        disabling the history, etc.

        The most comfortable way to implement this is using
        :py:func:`contextlib.contextmanager`:

        .. code-block:: python

            class Shell(rbot.machine.shell.Shell):
                @contextlib.contextmanager
                def _init_shell(self):
                    try:
                        # Wait for shell to appear
                        ...

                        # Setup options
                        ...

                        yield None
                    finally:
                        # Optionally destruct shell
                        ...
        """
        raise rbot.error.AbstractMethodError()

    @abc.abstractmethod
    def exec(self, *args: typing.Any) -> typing.Any:
        """
        Run a command using this shell.

        This is the only "common" interface rbot expects shells to implement.
        The exact semantics of running commands are up to the implementor.
        This especially includes the return value.

        :param \\*args: ``.exec()`` should take the command as one argument per
            command-line token.  For example:

            .. code-block:: python

                mach.exec("echo", "Hello", "World")

        :returns: The return value should in some way be related to the
            "output" of the command.  For
            :py:class:`~rbot.machine.linux.LinuxShell`, ``exec`` returns a
            tuple of the return code and console output: ``Tuple[int, str]``.
        """
        raise rbot.error.AbstractMethodError()


class RawShell(machine.Machine):
    """
    Absolute minimum shell implementation.

    :py:class:`RawShell` attempts to be a minimal shell implementation.  It
    does not make any assumptions about the other end.  It is used, for
    example, for raw board-console access which allows debugging before U-Boot
    is fully working.
    """

    @contextlib.contextmanager
    def _init_shell(self) -> typing.Iterator:
        yield None

    @property
    def prompt(self) -> typing.Optional[SearchString]:
        return self.ch.prompt

    @prompt.setter
    def prompt(self, new_prompt: SearchString) -> None:
        self.ch.prompt = new_prompt

    def interactive(self, ctrld_exit: bool = True) -> None:
        """
        Connect rbot's stdio to this machine's channel.  This will allow
        interactive access to the machine.
        """
        rbot.log.message(f"Entering interactive shell...")
        self.ch.attach_interactive(ctrld_exit=ctrld_exit)

    def read(
        self, n: int = -1, timeout: typing.Optional[float] = None
    ) -> typing.Optional[bytes]:
        try:
            return self.ch.read(n, timeout)
        except TimeoutError:
            return None

    def readline(
        self,
        timeout: typing.Optional[float] = None,
        lineending: typing.Union[str, bytes] = "\r\n",
    ) -> typing.Optional[str]:

        try:
            return self.ch.readline(timeout=timeout, lineending=lineending)
        except TimeoutError:
            return None

    def send(
        self,
        s: typing.Union[str, bytes],
        read_back: bool = True,
        timeout: typing.Optional[float] = None,
        _ignore_blacklist: bool = False,
    ) -> int:

        try:
            return self.ch.send(
                s,
                read_back=read_back,
                timeout=timeout,
                _ignore_blacklist=_ignore_blacklist,
            )
        except TimeoutError:
            return -1

    def exec(self, *args: str) -> None:
        self.sendline(" ".join(args))

    def sendline(
        self,
        s: typing.Union[str, bytes] = "",
        read_back: bool = True,
        timeout: typing.Optional[float] = None,
    ) -> typing.Optional[int]:

        try:
            return self.ch.sendline(s, read_back=read_back, timeout=timeout)
        except TimeoutError:
            return None

    def sendcontrol(self, c: str) -> bool:
        return self.ch.sendcontrol(c=c) > 0

    def sendeof(self) -> bool:
        return self.ch.sendeof() > 0

    def sendintr(self) -> bool:
        return self.ch.sendintr() > 0

    def expect_line(
        self,
        patterns: typing.Union[
            ConvenientSearchString, typing.List[ConvenientSearchString]
        ],
        timeout: typing.Optional[float] = None,
    ) -> bool:

        try:
            ret = self.ch.expect(patterns=patterns)
            return ret.i >= 0
        except TimeoutError:
            return False

    def read_until_prompt(
        self,
        prompt: typing.Optional[ConvenientSearchString] = None,
        timeout: typing.Optional[float] = None,
    ) -> typing.Optional[str]:
        try:
            return self.ch.read_until_prompt(prompt=prompt, timeout=timeout)
        except TimeoutError:
            return None
