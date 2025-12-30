import rbot
from rbot.machine import board, connector


class RaspberryPi(connector.PyserialConnector, board.Board):
    serial_port = "/dev/ttyUSB0"


class UuefiRaspberryPi(board.Connector, board.UefiAutobootIntercept, board.UefiShell):
    pass


def register_machines(ctx):
    ctx.register_machine(RaspberryPi, rbot.role.Board)
    ctx.register_machine(UuefiRaspberryPi, rbot.role.BoardUefi)
