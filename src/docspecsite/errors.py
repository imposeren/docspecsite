"""The errors and warnings that docspecsite reports to the user."""

from typing import override


class MessageWithValues(Exception):  # noqa: N818 -- the base of warnings too, not only of errors
    """Exception or warning with a static message and the values it is about.

    The first argument is a ``%``-style message template that never changes between occurrences (error trackers group
    by it); the further arguments are the values filled into it. ``str()`` gives the filled-in message.
    As with ``logging``, the template is only ``%``-formatted when values are given: without them ``%%`` stays as is.
    """

    message: str
    """See :meth:`.__init__`."""

    values: tuple[object, ...]
    """See :meth:`.__init__`."""

    def __init__(self, message: str, *values: object) -> None:
        """Hold a message template and its values.

        Args:
            message: Static ``%``-style template that never changes between occurrences, so error trackers group by
                it.
            *values: Values filled into the template with ``str()``; with none, the template is the message as is.
        """
        super().__init__(message, *values)
        self.message = message
        self.values = values

    @override
    def __str__(self) -> str:
        """Return the message with the values filled in."""
        return self.message % self.values if self.values else self.message


class DocspecsiteError(MessageWithValues):
    """Error in the docs, code or settings being processed, reported to the user as a message.

    Unlike any other exception, it is not a bug in docspecsite.
    """


class DocspecsiteWarning(MessageWithValues, UserWarning):
    """Warning about the docs or code being built that does not stop the build, such as an unresolvable link."""


class InternalErrorWarning(MessageWithValues, RuntimeWarning):
    """Warning for an unexpected exception, a bug in docspecsite, issued while that exception is handled."""
