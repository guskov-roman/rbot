import rbot

from rbot.machine import connector, board


class RaspberryPi(connector.ConsoleConnector, board.Board):

    def connect(self, mach):
        return mach.open_channel("picocom", "-b", "115200", "/dev/ttyUSB0")


class UefiRaspberryPi(board.Connector, board.UefiAutobootIntercept, board.UefiShell):
    pass


def register_machines(ctx):
    ctx.register_machine(RaspberryPi, rbot.role.Board)
    ctx.register_machine(UefiRaspberryPi, rbot.role.BoardUefi)
