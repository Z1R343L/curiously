# This file is part of curious.
#
# curious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# curious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with curious.  If not, see <http://www.gnu.org/licenses/>.

"""
Wrappers for Status objects.

.. currentmodule:: curious.dataclasses.presence
"""

import enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


class Status(enum.Enum):
    """
    Represents a Member's status.
    """

    #: Corresponds to online (green dot).
    ONLINE = "online"

    #: Corresponds to offline (gray dot).
    OFFLINE = "offline"

    #: Corresponds to idle (yellow dot).
    IDLE = "idle"

    #: Corresponds to Do Not Disturb (red dot).
    DND = "dnd"

    #: Corresponds to invisible (gray dot).
    INVISIBLE = "invisible"

    @property
    def strength(self) -> int:
        """
        :return: The strength of the presence, when computing the final presence on multiple \ 
            connections. 
        """
        return strengths.index(self)


strengths = [Status.OFFLINE, Status.INVISIBLE, Status.IDLE, Status.DND, Status.ONLINE]


class ActivityType(enum.IntEnum):
    """
    Represents a game's type.
    """

    #: Shows the ``Playing`` text.
    PLAYING = 0

    #: Shows the ``Streaming`` text.
    STREAMING = 1

    #: Shows the ``Listening to`` text.
    LISTENING_TO = 2

    #: Shows the ``Watching`` text.
    WATCHING = 3

    #: An unknown activity.
    UNKNOWN = 999999


class BasicActivity(object):
    """
    Represents a game object.
    """

    __slots__ = "_raw_type", "type", "url", "name"

    def __init__(self, **kwargs) -> None:
        """
        :param name: The name for the game. 100 characters max.
        :param url: The URL for the game, if streaming.
        :param type: A :class:`.GameType` for this game.
        """
        #: The raw activity type.
        self._raw_type = kwargs.get("type", 0)

        #: The type of game this is.
        self.type: ActivityType = ActivityType.PLAYING
        try:
            self.type = ActivityType(kwargs.get("type", 0))
        except ValueError:
            self.type = ActivityType.UNKNOWN

        #: The stream URL this game is for.
        self.url = kwargs.get("url", None)  # type: str
        #: The name of the game being played.
        self.name = kwargs.get("name", None)  # type: str

    def to_dict(self) -> dict:
        """
        :return: The dict representation of this object. 
        """
        d = {
            "name": self.name,
            "type": self.type,
        }
        if self.url is not None:
            d["url"] = self.url

        return d

    def __repr__(self) -> str:
        type_ = self.type.name
        return f"<{type(self).__name__} name='{self.name}' type={type_} url={self.url}>"


@dataclass(frozen=True)
class ActivityTimestamps:
    """
    Represents the timestamps for an activity.
    """

    #: The start timestamp for this activity.
    start: Optional[int] = None

    #: The end timestamp for this activity.
    end: Optional[int] = None


@dataclass(frozen=True)
class ActivityParty:
    """
    Represents the party for an activity.
    """

    #: The ID of the party.
    id: Optional[str] = None

    #: The size of the party.
    size: Optional[List[int]] = None


@dataclass(frozen=True)
class ActivityAssets:
    """
    Represents the assets for an activity.
    """

    #: The id for a large asset of the activity
    large_image: Optional[str] = None

    #: Text displayed when hovering over the large image of the activity
    large_text: Optional[str] = None

    #: The id for a small asset of the activity
    small_image: Optional[str] = None

    #: Text displayed when hovering over the small image of the activity
    small_text: Optional[str] = None


@dataclass(frozen=True)
class ActivitySecrets:
    """
    Represents the secrets for an activity.
    """

    join: Optional[str] = None
    spectate: Optional[str] = None
    match: Optional[str] = None


class RichActivity(BasicActivity):
    """
    Represents a rich presence activity.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if "application_id" not in kwargs:
            appid = None
        else:
            appid = int(kwargs["application_id"])

        #: The application ID for this rich activity.
        self.application_id: Optional[int] = appid

        #: The details for this rich activity.
        self.details: Optional[str] = kwargs.get("details")

        #: The state for this rich activity.
        self.state: Optional[str] = kwargs.get("state")

        #: If this rich activity is instanced.
        self.instanced: bool = kwargs.get("instanced", False)

        timestamps = kwargs.get("timestamps")
        if not timestamps:
            ts = None
        else:
            ts = ActivityTimestamps(**timestamps)

        #: The timestamps for this activity.
        self.timestamps: Optional[ActivityTimestamps] = ts

        party = kwargs.get("party")
        if not party:
            p = None
        else:
            p = ActivityParty(**party)

        #: The party for this activity.
        self.party: Optional[ActivityParty] = p

        assets = kwargs.get("assets")
        if not assets:
            a = None
        else:
            a = ActivityAssets(**assets)

        #: The assets for this activity.
        self.assets: Optional[ActivityAssets] = a

        secrets = kwargs.get("secrets")
        if not secrets:
            s = None
        else:
            s = ActivitySecrets(**secrets)

        #: The secrets for this activity.
        self.secrets: Optional[ActivitySecrets] = s

    def to_dict(self) -> Dict[str, Any]:
        base = {"state": self.state, "details": self.details, "instance": self.instanced}

        if self.timestamps:
            base["timestamps"] = {
                "start": self.timestamps.start,
                "end": self.timestamps.end,
            }

        if self.secrets:
            base["secrets"] = {
                "join": self.secrets.join,
                "match": self.secrets.match,
                "spectate": self.secrets.spectate,
            }

        if self.party:
            base["party"] = {
                "id": self.party.id,
                "size": self.party.size,
            }

        if self.assets:
            base["assets"] = {
                "large_image": self.assets.large_image,
                "large_text": self.assets.large_text,
                "small_image": self.assets.small_image,
                "small_text": self.assets.small_text,
            }

        return base


class ClientStatus(object):
    """
    Represents the specific client status for a user. This shows what status a user has for each
    platform (desktop, web, mobile).
    """

    def __init__(self, **client_status):
        self._client_status = client_status

    @property
    def desktop(self) -> Status:
        """
        :return: The :class:`.Status` for this user on the desktop.
        """
        return Status(self._client_status.get("desktop", "offline"))

    @property
    def mobile(self) -> Status:
        """
        :return: The :class:`.Status` for this user on mobile.
        """
        return Status(self._client_status.get("mobile", "offline"))

    @property
    def web(self) -> Status:
        """
        :return: The :class:`.Status` for this user on the web.
        """
        return Status(self._client_status.get("web", "offline"))


class Presence(object):
    """
    Represents a presence on a member.
    """

    __slots__ = "_status", "game", "client_status", "activities"

    def __init__(self, **kwargs) -> None:
        """
        :param status: The :class:`.Status` for this presence.
        :param game: The :class:`.Game` for this presence.
        """
        #: The :class:~.Status` for this presence.
        self._status = None  # type: Status
        # prevent dupe code by using our setter
        self.status = kwargs.get("status", Status.OFFLINE)

        #: The :class:`.ClientStatus` for this prescence.
        self.client_status = ClientStatus(**kwargs.get("client_status", {}))

        game = kwargs.get("game", None)
        if game:
            if "application_id" in game:
                game = RichActivity(**game)
            else:
                game = BasicActivity(**game)

        #: The game object for this presence.
        self.game: Optional[Union[BasicActivity, RichActivity]] = game

        #: The list of activities for this presence.
        self.activities: List[Union[BasicActivity, RichActivity]] = []

        for activity in kwargs.get("activities", []):
            if "application_id" in activity:
                ac = RichActivity(**activity)
            else:
                ac = BasicActivity(**activity)

            self.activities.append(ac)

    def __repr__(self) -> str:
        return "<Presence status={} game='{}'>".format(self.status, self.game)

    @property
    def status(self) -> Status:
        """
        :return: The :class:`.Status` associated with this presence.
        """
        return self._status

    @status.setter
    def status(self, value):
        if value is None:
            return

        if not isinstance(value, Status):
            value = Status(value)

        self._status = value

    @property
    def desktop(self) -> Status:
        """
        :return: The :class:`.Status` for this user on the desktop.
        """
        return self.client_status.desktop

    @property
    def mobile(self) -> Status:
        """
        :return: The :class:`.Status` for this user on mobile.
        """
        return self.client_status.mobile

    @property
    def web(self) -> Status:
        """
        :return: The :class:`.Status` for this user on the web.
        """
        return self.client_status.web

    @property
    def strength(self) -> int:
        """
        :return: The strength for this status.
        """
        return self.status.strength
