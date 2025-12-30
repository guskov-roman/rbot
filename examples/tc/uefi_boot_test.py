import rbot


@rbot.testcase
def uefi_test():
    with rbot.ctx.request(rbot.role.BoardUefi) as uefi:
        uefi.exec("help", "pci")
        ver = uefi.env("uefishellversion")
        rbot.log.info(f"UEFI Version: {ver}")
