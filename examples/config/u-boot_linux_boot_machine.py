import rbot
from rbot.machine import board, connector, linux


class RaspberryPi(connector.PyserialConnector, board.Board):

    serial_port = "/dev/ttyUSB0"


class UbootRaspberryPi(board.Connector, board.UBootAutobootIntercept, board.UBootShell):
    pass


class LinuxRaspberryPi(board.LinuxUbootConnector, linux.Bash):

    username = "roman"
    password = "foo"
    uboot = UbootRaspberryPi

    def do_boot(self, ub):
        ub.exec0("fdt", "addr", linux.Raw("${fdt_addr}"))
        ub.exec0("fdt", "get", "value", "bootargs", "/chosen", "bootargs")
        ub.env("kernel_comp_size", "0x0A000000")
        ub.exec0("fatload", "mmc", "0:1", linux.Raw("${kernel_addr_r}"), "kernel8.img")
        ub.env("kernel_comp_size", linux.Raw("${filesize}"))
        return ub.boot(
            "booti", linux.Raw("${kernel_addr_r}"), "-", linux.Raw("${fdt_addr}")
        )


def register_machines(ctx):
    ctx.register_machine(RaspberryPi, rbot.role.Board)
    ctx.register_machine(UbootRaspberryPi, rbot.role.BoardUBoot)
    ctx.register_machine(LinuxRaspberryPi, rbot.role.BoardLinux)
