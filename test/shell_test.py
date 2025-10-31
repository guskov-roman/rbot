from typing import Iterator, Match

import pytest

import rbot
from rbot.channel import channel, shell, common


@pytest.fixture
def ch() -> Iterator[channel.Channel]:
    with shell.ShellChannel() as ch:
        yield ch


def test_simple_command(ch: channel.Channel):
    ch.sendline("echo Hello Roman", read_back=True)
    out = ch.read()
    assert out.startswith(b"Hello Roman")


def test_simple_read(ch: channel.Channel):
    ch.write(b"0123456789ABCDEFGH")
    out = ch.read(10)
    assert out == b"0123456789"


def test_simple_iter(ch: channel.Channel):
    ch.write(b"12345678901234567890")
    string = bytearray()
    for new in ch.read_iter(10):
        string.extend(new)
    assert string == b"1234567890"
    for i in range(1, 10):
        c = ch.read(1)
        assert c == str(i).encode("utf-8")


def test_readline_cmd(ch: channel.Channel) -> None:
    ch.sendline("echo Hello; echo Roman", read_back=True)
    out_s = ch.readline()
    assert out_s == "Hello\n"
    out_s = ch.readline()
    assert out_s == "Roman\n"


def test_expect_cmd(ch: channel.Channel) -> None:
    ch.sendline("echo Ubuntu")
    res = ch.expect("Ubuntu")
    assert res.i == 0
    assert res.match == "Ubuntu"


def test_expect_cmd_list(ch: channel.Channel) -> None:
    ch.sendline("echo ubuntu Ipaddr")
    res = ch.expect(["Lol", "Ip"])
    assert res.i == 1
    assert res.match == "Ip"


def test_expect_cmd_re(ch: channel.Channel) -> None:
    ch.sendline("echo Ubuntu1337@test")
    res = ch.expect(["Test", common.Re(r"Ubuntu(\d{1,20})")])
    assert res.i == 1
    assert isinstance(res.match, Match), "Not a match object"
    assert res.match.group(1) == b"1337"


def test_borrowing(ch: channel.Channel) -> None:
    ch.sendline("echo Hello")

    with ch.borrow() as ch2:
        ch2.sendline("echo World")

        with pytest.raises(rbot.exceptions.ChannelBorrowedException):
            ch.sendline("echo Illegal")

    ch.sendline("echo back again")


def test_termination(ch: channel.Channel) -> None:
    ch.sendline("exit")
    with pytest.raises(rbot.exceptions.ChannelClosedException):
        ch.read_until_timeout(5)


def test_exec_command(ch: shell.ShellChannel):
    out = ch.exec("uname", "-a")
    assert out[0] == 0


def test_failing_bad_retcode(ch: shell.ShellChannel) -> None:
    with pytest.raises(rbot.exceptions.CommandFailureException):
        ch.exec0("unam", "-a")


def test_long_output(ch: shell.ShellChannel) -> None:
    s = "_".join(map(lambda i: f"{i:02}", range(80)))
    out = ch.exec0("echo", s)
    assert out == f"{s}\n", repr(out)
