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

import functools
import typing
import time

import rbot

if typing.TYPE_CHECKING:
    import mypy_extensions as mypy
else:

    class mypy:
        class KwArg:
            def __new__(cls, ty: typing.Any) -> None:
                pass

        class VarArg:
            def __new__(cls, ty: typing.Any) -> None:
                pass

        class DefaultArg:
            def __new__(cls, ty: typing.Any, name: typing.Optional[str] = None) -> None:
                pass


__all__ = ("testcase", "named_testcase")

F_tc = typing.TypeVar("F_tc", bound=typing.Callable[..., typing.Any])


def testcase(tc: F_tc) -> F_tc:
    """
    Decorate a function to make it a testcase.

    **Example**::

        @rbot.testcase
        def foobar_testcase(x: str) -> int:
            return int(x, 16)
    """

    @functools.wraps(tc)
    def wrapped(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        rbot.log.testcase_begin(tc.__name__)
        start = time.monotonic()
        ret = None
        try:
            ret = tc(*args, **kwargs)
        except Exception as e:
            import traceback

            trace = traceback.format_exc(limit=-6)
            rbot.log.exception(e.__class__.__name__, trace)
            rbot.log.testcase_end(tc.__name__, time.monotonic() - start, False)
        else:
            result = True if ret == 0 or ret is None else False
            rbot.log.testcase_end(tc.__name__, time.monotonic() - start, result)
        return ret

    setattr(wrapped, "_rbot_testcase", tc.__name__)
    return typing.cast(F_tc, wrapped)


def named_testcase(name: str) -> typing.Callable[[F_tc], F_tc]:
    """
    Decorate a function to make it a testcase, but with a different name.

    The testcase's name is relevant for log-events and when calling
    it from the commandline.

    **Example**::

        @rbot.named_testcase("my_different_testcase")
        def foobar_testcase(x: str) -> int:
            return int(x, 16)

    (On the commandline you'll have to run ``rbot my_different_testcase`` now.)
    """

    def _named_testcase(tc: F_tc) -> F_tc:
        @functools.wraps(tc)
        def wrapped(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            with rbot.testcase(name):
                return tc(*args, **kwargs)

            # This line will only be reached when a testcase was skipped.
            # Return `None` as the placeholder return value.
            return None

        setattr(wrapped, "_rbot_testcase", name)
        return typing.cast(F_tc, wrapped)

    return _named_testcase
