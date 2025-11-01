import functools
import typing
import inspect

channel_tc = typing.TypeVar("channel_tc", bound=typing.Callable[..., typing.Any])

def channel(rbot_ch: channel_tc) -> channel_tc:

    @functools.wraps(rbot_ch)
    def wrapped(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        return rbot_ch(*args, **kwargs)

    setattr(wrapped, "_rbot_channel", rbot_ch.__name__)
    return typing.cast(channel_tc, wrapped)


F_tc = typing.TypeVar("F_tb", bound=typing.Callable[..., typing.Any])

def testcase(tc: F_tc) -> F_tc:

    @functools.wraps(tc)
    def wrapped(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        return tc(*args, **kwargs)

    setattr(wrapped, "_rbot_testcase", tc.__name__) 
    return typing.cast(tc, wrapped)
