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

import rbot
import sys
import pathlib
import types


def load_module(p: pathlib.Path) -> types.ModuleType:
    """
    Load a python module from a path.

    :param pathlib.Path p: Path to ``<module>.py``
    :rtype: Module
    """
    import importlib.util
    import importlib.abc

    if not p.is_file():
        raise FileNotFoundError(f"The module {str(p)!r} does not exist")
    default_sys_path = sys.path
    try:
        module_spec = importlib.util.spec_from_file_location(
            name=p.stem, location=str(p)
        )
        module = importlib.util.module_from_spec(module_spec)  # type: ignore
        if not isinstance(module_spec.loader, importlib.abc.Loader):  # type: ignore
            raise TypeError(f"Invalid module spec {module_spec!r}")
        sys.path = default_sys_path + [str(p.parent)]
        module_spec.loader.exec_module(module)  # type: ignore
    finally:
        sys.path = default_sys_path

    return module


def load_config(config: str, ctx: "rbot.Context") -> None:

    module = load_module(pathlib.Path(config).resolve())
    if not hasattr(module, "register_machines"):
        raise AttributeError(f"{config} is missing `register_machines()`")
    getattr(module, "register_machines")(ctx)


def load_testcase(file: str, ctx: "rbot.Context") -> None:
    module = load_module(pathlib.Path(file).resolve())
    for f in module.__dict__.values():
        if hasattr(f, "_rbot_testcase"):
            name = getattr(f, "_rbot_testcase")
            test = getattr(module, name)
            ctx.register_testcase(test)
