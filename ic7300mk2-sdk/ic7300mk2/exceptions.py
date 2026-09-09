"""Exception hierarchy for the ic7300mk2 SDK."""


class Ic7300Error(Exception):
    """Base class for all SDK errors."""


class ConnectionFailed(Ic7300Error):
    """The network session could not be established or was lost."""


class AuthError(ConnectionFailed):
    """The radio rejected the supplied username/password."""


class RadioBusy(ConnectionFailed):
    """Another client already holds the radio's streams."""


class NotConnected(Ic7300Error):
    """A command was issued before connect() or after the session dropped."""


class CommandTimeout(Ic7300Error):
    """The radio did not answer a CI-V command within the timeout."""


class CommandRejected(Ic7300Error):
    """The radio returned NG (0xFA) for the command."""

    def __init__(self, command: bytes):
        self.command = command
        super().__init__("radio rejected command " + command.hex(" "))
