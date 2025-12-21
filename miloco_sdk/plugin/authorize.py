import base64
import hashlib
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlencode

import aiohttp
import requests
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from miloco_sdk.base import BaseApi
from miloco_sdk.utils.const import MICO_REDIRECT_URI

OAUTH2_CLIENT_ID: str = "2882303761520431603"

# device_uuid = uuid.uuid4().hex
device_uuid = "ad808a752fb142079bc789f7a6c15ac8"
PROJECT_CODE: str = "mico"


class Authorize(BaseApi):

    def gen_auth_url(
        self,
        scope: Optional[List] = None,
        skip_confirm: Optional[bool] = False,
        redirect_uri: Optional[str] = None,
    ) -> str:
        """Get auth url.
        https://dev.mi.com/xiaomihyperos/documentation/detail?pId=1708
        """
        OAUTH2_AUTH_URL: str = "https://account.xiaomi.com/oauth2/authorize"

        params: Dict = {
            "redirect_uri": redirect_uri or MICO_REDIRECT_URI,
            "client_id": OAUTH2_CLIENT_ID,
            "response_type": "code",
            "device_id": self._client._device_id,
            "state": self._client._state,
        }
        if scope:
            params["scope"] = " ".join(scope).strip()
        params["skip_confirm"] = skip_confirm
        encoded_params = urlencode(params)

        return f"{OAUTH2_AUTH_URL}?{encoded_params}"

    def refresh_access_token_from_mico(self, refresh_token: str) -> str:

        data = {
            "client_id": OAUTH2_CLIENT_ID,
            "redirect_uri": MICO_REDIRECT_URI,
            "refresh_token": refresh_token,
        }
        oauth_host: str = f"{PROJECT_CODE}.api.mijia.tech"

        res = requests.get(
            url=f"https://{oauth_host}/app/v2/{PROJECT_CODE}/oauth/get_token",
            params={"data": json.dumps(data)},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        return res.json()

    def get_access_token_from_mico(self, code: str) -> str:
        data = {
            "code": code,
            "client_id": OAUTH2_CLIENT_ID,
            "device_id": self._client._device_id,
            "redirect_uri": MICO_REDIRECT_URI,
        }

        oauth_host: str = f"{PROJECT_CODE}.api.mijia.tech"

        res = requests.get(
            url=f"https://{oauth_host}/app/v2/{PROJECT_CODE}/oauth/get_token",
            params={"data": json.dumps(data)},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        return res.json()
