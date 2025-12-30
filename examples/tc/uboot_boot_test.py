import rbot


@rbot.testcase
def uboot_test():
    with rbot.ctx.request(rbot.role.BoardUBoot) as ub:
        _, out = ub.exec("pci")
        rbot.log.message(out)
        board = ub.env("board_name")
        rbot.log.info(f"Board: Raspberry Pi {board}")
