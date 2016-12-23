import typing

from curious.dataclasses.role import Role
from curious.dataclasses.status import Game, Status
from curious.dataclasses.user import User
from curious.dataclasses import guild


class Member(User):
    """
    A member is a user attached to a guild.
    """
    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs.get("user"))

        #: A dictionary of roles this user has.
        self._roles = {}

        #: The date the user joined the guild.
        # TODO: Make this a datetime.
        self.joined_at = kwargs.pop("joined_at", None)

        #: The member's current nickname.
        self.nickname = kwargs.pop("nickname", None)

        #: The member's current guild.
        self.guild = None  # type: guild.Guild

        #: The current game this Member is playing.
        self.game = None  # type: Game

        #: The current status of this member.
        self._status = None  # type: Status

    @property
    def status(self) -> Status:
        return self._status

    @status.setter
    def status(self, value):
        self._status = Status(value)

    @property
    def roles(self) -> typing.Iterable[Role]:
        """
        :return: A list of roles this user has.
        """
        return self._roles.values()

    @property
    def colour(self) -> int:
        """
        :return: The computed colour of this user.
        """
        roles = sorted(self.roles, key=lambda r: r.position, reverse=True)
        roles = filter(lambda role: role.colour, roles)
        try:
            return next(roles).colour
        except StopIteration:
            return 0
