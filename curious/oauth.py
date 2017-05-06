"""
A module that assists with implementing the Discord OAuth2 flow.
"""
import enum
import base64
import json
import secrets
import typing

import collections

import datetime

from oauthlib.oauth2 import OAuth2Error
from oauthlib.oauth2.rfc6749.clients import WebApplicationClient

from curious.http.curio_http import ClientSession, Response
from curious.exc import HTTPException


class InvalidStateError(Exception):
    """
    Raised from :meth:`.OAuth2Handshaker.fetch_token` if the state is invalid
    """
    pass


class OAuth2Scope(enum.Enum):
    """
    OAuth2 scopes.
    """
    #: Authorizes a bot into a guild.
    BOT = 'bot'
    #: Allows access to the connections of a user.
    CONNECTIONS = 'connections'
    #: Allows access to basic user info.
    IDENTIFY = 'identify'
    #: Allows access to basic user info + their email.
    EMAIL = 'email'
    #: Allows access to user guild objects for this user.
    GUILD = 'guild'


class OAuth2Token(object):
    """
    Represents a token returned from the Discord OAuth2 API.
    """

    def __init__(self, token_type: str, scope: str,
                 access_token: str, refresh_token: str, expiration_time: datetime.datetime):
        #: The token type of the token (normally ``Bearer``).
        self.token_type = token_type

        #: A list of :class:`~.OAuth2Scope` this token is authenticated for.
        self.scopes = []
        for scope_name in scope.split(" "):
            self.scopes.append(OAuth2Scope(scope_name))

        #: The actual access token to be used.
        self.access_token = access_token

        #: The refresh token to be used during a refresh.
        self.refresh_token = refresh_token

        #: The time this token expires at.
        self.expiration_time = expiration_time

    @classmethod
    def from_dict(cls, d: dict) -> 'OAuth2Token':
        """
        Creates a token from a dict, similar to one provided by the token endpoint.
        """
        print(d)
        if "expiration_time" not in d:
            expiration_time = datetime.datetime.utcnow() + \
                              datetime.timedelta(seconds=d["expires_in"])
            d["expiration_time"] = expiration_time

        d.pop("expires_in", None)

        c = cls(**d)
        return c

    @property
    def expired(self) -> bool:
        return self.expiration_time < datetime.datetime.utcnow()


class OAuth2Client(object):
    """
    The class used to perform an OAuth2 handshake with Discord.
    This will provide a URL that can be used to authorize a client, and then the ability to fetch a
    new :class:`~.OAuth2Token`.
    
    .. code-block:: python
    
        # note: we can't fetch the client ID automatically, unlike in regular bots :(
        # so you have to pass it manually
        # if you have a bot running alongside this, you can use the Client ID from that, however.
        my_client = OAuth2Client(my_client_id, my_client_secret)
        
        url = my_client.get_authorization_url(scopes=[OAuthScope.IDENTITY])
        # get the user to give back the state and the code
        # ...
        token = await my_client.get_token(state, code)
        
        # some time later
        user = await my_client.get_user()

    
    :param client_id:
        The Client ID of the application.
        
        .. warning::
            For **old bots**, this is NOT the Bot ID.
     
    :param client_secret: 
        The client secret of the application.
        
        ..warning::
            This is **not** your token.
            
    :param redirect_uri: 
        The URL the client will be redirected to after authorizing your application.  
        This is then used to retrieve the state.
    """

    BASE = "https://discordapp.com"
    API_BASE = BASE + "/api/v7"
    AUTHORIZE_URL = BASE + "/oauth2/authorize"
    TOKEN_URL = API_BASE + "/oauth2/token"

    def __init__(self, client_id: int, client_secret: str,
                 redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        self._oauth2_client = WebApplicationClient(client_id=self.client_id,
                                                   redirect_url=self.redirect_uri)
        self.sess = ClientSession()

        #: A list of states that have been seen before.
        #: If the state was not seen, it will raise an invalid state error.
        self._states = collections.deque(maxlen=500)

    def _get_state(self):
        return secrets.token_urlsafe(16)

    def get_authorization_url(self, scopes: typing.List[OAuth2Scope]):
        """
        Gets the authorization URL to be used for the user to authorize this application.
        
        :param scopes: A list of :class:`~.OAuthScope` for the request. 
        """
        url = self._oauth2_client.prepare_request_uri(self.AUTHORIZE_URL,
                                                      scope=[scope.value for scope in scopes],
                                                      redirect_uri=self.redirect_uri,
                                                      state=self._get_state())
        return url

    async def fetch_token(self, code: str, state: str):
        """
        Fetches the token when given an authorization code and state.
        
        :param code: The authorization code returned in the URI. 
        :param state: The state returned in the URI.
        :return: A :class:`~.OAuthToken` object representing the token.
        """
        # if state not in self._states:
        #    raise InvalidStateError(state)
        # construct the URI we need to send
        uri = self._oauth2_client.prepare_request_uri(self.TOKEN_URL,
                                                      code=code,
                                                      redirect_uri=self.redirect_uri,
                                                      client_secret=self.client_secret,
                                                      grant_type="authorization_code")
        response = await self.sess.post(uri)
        if response.status_code != 200:
            raise OAuth2Error(response, await response.json())

        # construct the token
        token = OAuth2Token.from_dict(await response.json())
        return token

    async def refresh_token(self, token: typing.Union[OAuth2Token, str],
                            scopes: typing.List[OAuth2Scope] = None) -> OAuth2Token:
        """
        Refreshes a token.
        
        :param token: Either a :class:`~.OAuth2Token` or the str refresh token.
        :param scopes: The scopes to request.
            If an OAuth2Token is passed as the token, this will be fetched automatically.
        :return: The refreshed :class:`~.OAuth2Token`.
        """
        if isinstance(token, OAuth2Token):
            ref = OAuth2Token.refresh_token
            scopes = [scope.name.lower() for scope in token.scopes]
        else:
            ref = token
            scopes = [scope.name.lower() for scope in scopes] if scopes else None

        uri, headers, body = self._oauth2_client.prepare_refresh_token_request(
            self.TOKEN_URL, refresh_token=ref, scope=scopes
        )

        response = await self.sess.post(uri, headers=list(headers.items()), body=body)

        self._oauth2_client.parse_request_body_response(body=await response.text())
        token = OAuth2Token.from_dict(await response.json())
        return token