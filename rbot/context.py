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


import collections
import contextlib
import typing
from typing import (
    Any,
    Callable,
    ContextManager,
    DefaultDict,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import rbot
import rbot.error
import rbot.role
from rbot import machine

M = TypeVar("M", bound=machine.Machine)


class InstanceManager(Generic[M]):
    def __init__(self) -> None:
        self._cx = contextlib.ExitStack()
        self._current_users = 0
        self._instance: Optional[M] = None
        self._available = False

    def init(
        self,
        *,
        context: Optional[ContextManager[M]] = None,
        instance: Optional[M] = None,
    ) -> None:
        if self._instance is not None:
            raise rbot.error.ContextError("trying to re-initialize a live instance")

        self._cx = contextlib.ExitStack()
        self._available = True

        if instance is not None and context is not None:
            raise ValueError("cannot have both `context` and `instance` arguments")
        elif instance is not None:
            self._instance = self._cx.enter_context(instance)  # type: ignore
        elif context is not None:
            self._instance = self._cx.enter_context(context)
        else:
            raise ValueError("needs either `context` or `instance` argument")

    def teardown(self) -> None:
        if self._instance is None:
            raise rbot.error.ContextError("trying to de-init a closed instance")

        # Necessary to ensure any open contexts for this machine do not
        # prevent it from running its deinitialization code:
        self._instance._rc = 1

        self._cx.close()
        self._instance = None

    @contextlib.contextmanager
    def request(self, exclusive: bool = False, keep_alive: bool = False) -> Iterator[M]:
        if self._instance is None:
            raise rbot.error.ContextError("trying to access a closed instance")

        if not self._available:
            raise rbot.error.ContextError(
                "trying to access instance which is not available"
            )

        try:
            self._current_users += 1

            if exclusive:
                # Mark the instance as exclusively used so no future request()
                # will succeed.
                self._available = False

            with self._instance as m:
                yield m
        finally:
            self._current_users -= 1

            if exclusive or (not keep_alive and self._current_users == 0):
                # If we were the last user or the request() was an exclusive
                # one, tear down this instance now.  Future requests will then
                # need to re-initilize it.
                if self.is_alive():
                    self.teardown()

    def is_alive(self) -> bool:
        return self._instance is not None

    def has_users(self) -> bool:
        return self._current_users != 0


class Context(typing.ContextManager):
    """
    A context which machines can be registered in and where instances can be retrieved from.

    You will usually access the global context :py:data:`rbot.ctx` which is an
    instance of this class instead of instantiating :py:class:`rbot.Context`
    yourself.  See the :ref:`context` guide for a detailed introduction.

    In case you do need to construct a context yourself, there are a few
    customization possibilities:

    :param bool keep_alive: Whether machines should be immediately
        de-initialized once their context-manager is exited or whether they
        should be "kept alive" for a future request to immediately re-access
        them.

        .. warning::

            Keeping instances alive can have unintended side-effects:  If, for
            example, a test brings a machine into an unusable state and then
            fails, a followup testcase could gain access to the same broken
            instance without reinitialization.

            To avoid such problems, always write testcase to leave the instance
            in a clean state.  If a testcase can't guarantee this, it should
            request the instance with ``reset_on_error=True`` or even
            ``exclusive=True``.
    :param bool add_defaults: Add default machines for some roles from
        :py:mod:`rbot.role`, for example for :py:class:`rbot.role.LocalHost`.
        Defaults to ``False``.
    :param bool reset_on_error_by_default: Set ``reset_on_error=True`` for all
        ``request()`` s which do not explicitly overwrite it.  It is a good idea
        to set this in conjunction with ``keep_alive=True``.
    """

    def __init__(
        self,
        *,
        keep_alive: bool = False,
        add_defaults: bool = False,
        reset_on_error_by_default: bool = False,
    ) -> None:
        self._roles: Dict[Type[rbot.role.Role], Type[machine.Machine]] = {}
        self._testcases: Dict[str, typing.Callable] = {}
        self._weak_roles: Set[Type[rbot.role.Role]] = set()
        self._open_contexts = 0
        self._keep_alive = keep_alive
        self._reset_on_error_default = reset_on_error_by_default
        self._teardown_order: List[Type] = []

        self._instances: DefaultDict[Type[machine.Machine], InstanceManager] = (
            collections.defaultdict(InstanceManager)
        )

        if add_defaults:
            rbot.role._register_default_machines(self)

    @property
    def testcases(self) -> typing.Dict[str, typing.Callable]:
        return self._testcases

    def register_testcase(self, test: typing.Callable) -> None:
        if not callable(test):
            raise KeyError(
                f"Testcase can only be a function or class inherited from the test class"
            )

        key = test.__wrapped__.__name__  # type: ignore

        if key in self._testcases:
            raise KeyError(f"Testcase with name: {key} is already registered")

        self._testcases[key] = test

    def run_test(self, stop_on_fail: bool = True):

        aggr_result: int = 0

        for key in self._testcases:
            ret = self._testcases[key]()

            if not isinstance(ret, int):
                ret = 0

            if ret > aggr_result:
                aggr_result = ret

            if stop_on_fail and ret > 0:
                break

        return aggr_result

    def register_machine(
        self,
        machine: Type[M],
        roles: Union[Any, List[Any]],
        *,
        weak: bool = False,
        add_role: bool = False,
    ) -> None:
        """
        Register a machine in this context for certain roles.

        Registers the machine-class ``machine`` for the role ``roles`` or, if
        ``roles`` is a list, for all roles it contains.  If for any role
        a machine is already registered, an exception is thrown.

        This function is usually called in the ``register_machines()`` function
        of a lab- or board-config:

        .. code-block:: python

            class SomeLabHostClass(...):
                ...

            def register_machines(ctx: rbot.Context) -> None:
                ctx.register(SomeLabHostClass, rbot.role.LabHost)

                # or, to register for multiple roles
                ctx.register(SomeLabHostClass, [rbot.role.LabHost, rbot.role.BuildHost])

        :param machine: A concrete machine-class to be registered.  This
            machine-class will later be instantiated on request via its
            :py:meth:`Connector.from_context()
            <rbot.machine.connector.Connector.from_context()>` classmethod.
        :param roles: Either a single role or a list of roles for which
            ``machine`` should be registered.
        :param bool weak: Changes the way registration works:  The machine is
            only registered for those roles which do not already have a machine
            registered.  It will be registered as a weak default which means
            a later register will overwrite it without erroring.  This is
            usually not necessary and should be used with care.
        """
        if not isinstance(roles, list):
            roles = [roles]

        for role in roles:
            if not issubclass(role, rbot.role.Role):
                rbot.error.RbotException(f"{role!r} is not a role")

            if role in self._roles:
                if weak:
                    continue
                elif role in self._weak_roles:
                    # Overwrite the weak default
                    self._weak_roles.discard(role)
                else:
                    raise KeyError(
                        f"a machine is already registered for role {rbot.role.rolename(role)}"
                    )

            if weak:
                self._weak_roles.add(role)
            self._roles[role] = machine

        if not hasattr(rbot.role, role.__qualname__):
            rbot.log.warning(
                f"Register machine '{machine.__qualname__}' with role '{role.__qualname__}'"
            )
            setattr(rbot.role, role.__qualname__, role)

    def _get_class_and_instance(
        self, type: Callable[..., M]
    ) -> Tuple[Type[M], InstanceManager]:
        type = typing.cast(Type[M], type)

        if type in self._roles:
            role = typing.cast(Type[rbot.role.Role], type)
            machine_class = typing.cast(Type[M], self._roles[role])
        elif type in self._instances:
            machine_class = type
        else:
            raise rbot.error.MachineNotFoundError(f"no machine found for {type!r}")

        instance = self._instances[machine_class]

        return (machine_class, instance)

    @contextlib.contextmanager
    def request(
        self,
        type: Callable[..., M],
        *,
        reset: bool = False,
        exclusive: bool = False,
        reset_on_error: Optional[bool] = None,
    ) -> Iterator[M]:
        """
        Request a machine instance from this context.

        Requests an instance of the :ref:`role <rbot_role>` ``type`` from the
        context.  If no instance exists, one will be created.  If a previous
        testcase has already requested such an instance, the same instance is
        returned (this behavior can be controlled with the ``reset`` and
        ``exclusive`` keyword arguments).

        This function must be used as a context manager:

        .. code-block:: python

            @rbot.testcase
            def foo_bar():
                with rbot.ctx.request(rbot.role.LabHost) as lh:
                    lh.exec0("uname", "-a")

        Alternatively, if you need multiple machines, a pattern similar to
        :py:class:`contextlib.ExitStack` can be used:

        .. code-block:: python

            @rbot.testcase
            def foo_bar():
                with rbot.ctx() as cx:
                    lh = cx.request(rbot.role.LabHost)
                    bh = cx.request(rbot.role.BuildHost)

                    lh.exec0("cat", "/etc/os-release")
                    bh.exec0("free", "-h")

        The semantics of a ``request()`` can be controlled further by the
        ``reset``, ``exclusive``, and ``reset_on_error`` keyword arguments.
        See their documentation for the details.

        :param rbot.role.Role type: The :ref:`role <rbot_role>` for which a machine instance
            is requested.

        :param bool reset: Controls what happens if an instance already exists:

            - ``False`` (default): If an instance already exists due to a
              previous **request()**, it will be returned (both requests
              *share* it).
            - ``True``: If an instance already exists due to a previous
              **request()**, it will be torn down and re-initialized (the
              previous request thus looses access to it).

            ``reset=True`` can, for example, be used to write a testcase where
            the DUT is powercycled:

            .. code-block:: python

                @rbot.testcase
                def test_with_reboot():
                    with rbot.ctx.request(rbot.role.BoardUBoot) as ub:
                        ub.exec0("version")

                    # Device will be powercycled here, even though if some "outer"
                    # context for U-Boot is still active.  Note that such an outer
                    # context will loose access to the instance after this point.

                    with rbot.ctx.request(rbot.role.BoardUBoot, reset=True) as ub:
                        ub.exec0("version")

        :param bool exclusive: Controls whether other requests can get
            access to the same instance while this request is active:

            - ``False`` (default): A **request()** after this one will get
              *shared* access to the same instance.
            - ``True``: Any future **request()** while this one is active is
              forbidden and will fail.  Once this **request()** ends, the
              instance will be torn down so future requests will need to
              re-initialize it.

            This mode should be used when you are going to do changes to the
            instance which could potentially bring it into a state that other
            testcases won't expect.

        :param bool reset_on_error:  Controls behavior when the context-manager
            returned by this ``request()`` is exited abnormally via an exception:

            - ``False`` (default):  The exception is ignored (and just
              propagates further up), no special behavior.
            - ``True``: Instructs the ``Context`` to forcefully de-initialize
              this instance if the context-manager returned from this
              ``request()`` was exited with an exception.  The exception is
              then of course propagated further up.

            This can be useful to ensure a follow-up request will always get a
            clean instance, even when something went wrong here.  This is
            especially relevant for a :py:class:`Context` which has
            ``keep_alive=True``.

            If ``exclusive=True``, ``reset_on_error=True`` is essentially a no-op.

            The default might be ``True`` if the :py:class:`~rbot.Context` was
            instantiated with ``reset_on_error_by_default=True``.
        """
        if reset_on_error is None:
            reset_on_error = self._reset_on_error_default

        if self._keep_alive and self._open_contexts == 0:
            raise rbot.error.ContextError(
                "When a context is marked with `keep_alive` you **must** enter "
                + "its own context-manager to ensure proper cleanup."
            )

        machine_class, instance = self._get_class_and_instance(type)

        if instance.is_alive() and reset:
            # Requester wants the machine to be re-initialized if it is already alive.
            instance.teardown()

        if not instance.is_alive():
            instance.init(context=machine_class.from_context(self))

        with instance.request(exclusive, self._keep_alive) as m:
            assert isinstance(m, machine_class), f"machine type mismatch"

            if machine_class not in self._teardown_order:
                self._teardown_order.append(machine_class)

            try:
                yield m
            except BaseException as e:
                if reset_on_error:
                    if (
                        e.__class__.__name__ == "Skipped"
                        and e.__class__.mro()[1].__module__ == "_pytest.outcomes"
                    ):
                        rbot.log.warning(
                            "Ignoring `reset_on_error` because exception was from pytest.skip()"
                        )
                    else:
                        if instance.is_alive():
                            instance.teardown()
                raise e from None

    def get_machine_class(self, type: Callable[..., M]) -> Type[M]:
        """
        Return the registered machine class for a :py:class:`~rbot.role.Role`.
        """
        role = typing.cast(Type[rbot.role.Role], type)
        return typing.cast(Type[M], self._roles[role])

    def teardown_if_alive(self, type: Callable[..., M]) -> bool:
        """
        Tear down any existing machine instances for a certain role.

        This is useful, for example, when there might be a ``BoardLinux``
        instance active and you need to get into ``BoardUBoot``.

        :returns: Boolean whether an instance was alive and torn down
            (``True``) or whether no instance was alive (``False``).

        """
        _, instance = self._get_class_and_instance(type)

        if instance.is_alive():
            instance.teardown()
            return True
        else:
            return False

    @contextlib.contextmanager
    def reconfigure(
        self,
        *,
        keep_alive: Optional[bool] = None,
        reset_on_error_by_default: Optional[bool] = None,
    ) -> "Iterator[Context]":
        """
        Temporarily reconfigure this context (e.g. ``keep_alive`` flag).

        This method allows you to temporarily change flags for this context and
        have them restored afterwards.  For example, this can be useful for
        running a test-suite with the ``keep_alive`` and ``reset_on_error``
        flags enabled.

        **Example**:

        .. code-block:: python

            with ctx.reconfigure(keep_alive=True):
                ...

        Once the reconfiguration context-manager exits, the old state will be
        restored.  This especially means that any machines which were kept
        alive due to the reconfiguration (but have no active outside users)
        will be torn down before returning to the old state.

        """
        keep_alive_orig = self._keep_alive
        reset_on_error_orig = self._reset_on_error_default
        try:
            if keep_alive is not None:
                self._keep_alive = keep_alive
            if reset_on_error_by_default is not None:
                self._reset_on_error_default = reset_on_error_by_default

            yield self
        finally:
            self._keep_alive = keep_alive_orig
            self._reset_on_error_default = reset_on_error_orig

            # If the previous configuration did not enable keep_alive, we need
            # to tear down all the machines which are still alive but have no
            # users.
            if keep_alive_orig is False and keep_alive is True:
                for cls in reversed(self._teardown_order):
                    inst = self._instances[cls]
                    if inst.is_alive() and not inst.has_users():
                        inst.teardown()

    def is_active(self) -> bool:
        """
        Check whether this context was already "activated" by entering it.

        For the :py:class:`rbot.Context` to work properly, it should be entered
        as a context-manager at least once (but it is okay to do it multiple
        times):

        .. code-block:: python

            with rbot.ctx:
                ...

        ``is_active()`` can be used to check if this has already happened.
        This can be used as an indication whether the context was already
        initialized or not.  If it wasn't, you probably need to register
        machines for this context first (for example by loading configuration
        modules).

        """
        return self._open_contexts != 0

    @contextlib.contextmanager
    def __call__(self) -> "Iterator[ContextHandle]":
        with contextlib.ExitStack() as exitstack:
            handle = ContextHandle(self, exitstack)
            yield handle

    def __enter__(self) -> "Context":
        self._open_contexts += 1
        return self

    def __exit__(self, *args: Any) -> None:
        try:
            if self._open_contexts == 1:
                for cls in reversed(self._teardown_order):
                    inst = self._instances[cls]
                    if inst.is_alive():
                        if self._keep_alive:
                            # If we kept instances alive, now is a good time to
                            # finally tear them down; there won't be any users
                            # after this point...
                            inst.teardown()
                        else:
                            rbot.log.warning(
                                f"Found dangling {cls!r} instance in this context"
                            )
        finally:
            if self._open_contexts == 1:
                for cls, inst in self._instances.items():
                    if inst.is_alive():
                        rbot.log.warning(
                            f"Teardown went wrong!  A {cls!r} instance is still alive.\n"
                        )
            self._open_contexts -= 1


T = TypeVar("T")


class ContextHandle:
    def __init__(self, ctx: Context, exitstack: contextlib.ExitStack) -> None:
        self.ctx = ctx
        self._exitstack = exitstack

    def request(
        self,
        type: Callable[..., M],
        *,
        reset: bool = False,
        exclusive: bool = False,
        reset_on_error: Optional[bool] = None,
    ) -> M:
        return self.enter_context(
            self.ctx.request(
                type, reset=reset, exclusive=exclusive, reset_on_error=reset_on_error
            )
        )

    def get_machine_class(self, type: Callable[..., M]) -> Type[M]:
        return self.ctx.get_machine_class(type)

    def enter_context(self, context: ContextManager[T]) -> T:
        return self._exitstack.enter_context(context)
