import json
import time
from typing import Dict, List, Optional
from urllib.parse import urlencode

from qrcode import QRCode

from miloco_sdk.base import BaseApi
from miloco_sdk.utils.const import MICO_REDIRECT_URI

OAUTH2_CLIENT_ID: str = "2882303761520431603"

# device_uuid = uuid.uuid4().hex
device_uuid = "ad808a752fb142079bc789f7a6c15ac8"
PROJECT_CODE: str = "mico"


class Authorize(BaseApi):

    @staticmethod
    def _print_qr(loginurl: str, box_size: int = 10):

        qr = QRCode(border=1, box_size=box_size)
        qr.add_data(loginurl)
        try:
            qr.print_ascii(invert=True, tty=True)
        except OSError:
            qr.print_ascii(invert=True, tty=False)

    def get_code_url(self) -> str:

        auth_url = "https://account.xiaomi.com/oauth2/authorize"
        params = {
            "pt": "0",
            "skip_confirm": False,
            "response_type": "code",
            "redirect_uri": MICO_REDIRECT_URI,
            "state": self._client._state,
            "client_id": OAUTH2_CLIENT_ID,
            "scope": "1 3 6000",
            "scope_provider": "",
            "_locale": "zh_CN",
            "_json": "true",
        }
        auth_res = self._client._http.get(auth_url, params=params, allow_redirects=False)
        auth_json = json.loads(auth_res.text.split("&&&START&&&")[1])

        # 获取登录二维码
        url = "https://account.xiaomi.com/longPolling/loginUrl"
        scopes = list(auth_json["data"]["scope"].values())
        params = {
            "sid": auth_json["data"]["sid"],
            "lsrp_appName": auth_json["data"]["lsrp_appName"],
            "_customDisplay": "20",
            "scope": "1 6000",
            "client_id": OAUTH2_CLIENT_ID,
            "_locale": "zh_CN",
            "callback": auth_json["data"]["callback"],
            "serviceParam": '{"checkSafePhone":false,"checkSafeAddress":false,"lsrp_score":0.0}',
            "showActiveX": "false",
            "theme": "",
            "needTheme": "false",
            "bizDeviceType": "",
            "scopes": json.dumps(scopes),
            "_hasLogo": "false",
            "_qrsize": "240",
            "_dc": str(int(time.time() * 1000)),
        }
        login_res = self._client._http.get(url, params=params, timeout=10)
        login_json = json.loads(login_res.text.split("&&&START&&&")[1])

        # 打印 登录二维码
        self._print_qr(login_json["loginUrl"])
        print("可以通过扫码登录，也可以通过在浏览器中打开授权链接: ", login_json["loginUrl"])

        # 等待扫码登录，该接口为长轮询接口，会返回登录二维码
        lp_res = self._client._http.get(login_json["lp"], timeout=120)
        lp_json = json.loads(lp_res.text.split("&&&START&&&")[1])

        # 请求  /sts/oauth 获取 cookies
        self._client._http.get(lp_json["location"], allow_redirects=False)

        # 获取 code
        auth_url = "https://account.xiaomi.com/oauth2/authorize"

        params = {
            "redirect_uri": "https://mico.api.mijia.tech/login_redirect",
            "client_id": OAUTH2_CLIENT_ID,
            "response_type": "code",
            "device_id": self._client._device_id,
            "state": self._client._state,
            "skip_confirm": "False",
            "_locale": "zh_CN",
            # "nonce": "eaacrXG2gHUBwTkc",
            # "sign": "XsnFT1AFnoiE9wAI+JhlEgpyEeM=",
            "scope": "1 3 6000",
            "userId": str(lp_json["userId"]),
            "_from_user_authorize": "true",
            "confirmed": "true",
        }

        response = self._client._http.get(auth_url, params=params, allow_redirects=False)
        return response.headers["Location"]

    def gen_auth_url(
        self,
        scope: Optional[List] = None,
        skip_confirm: Optional[bool] = True,
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

        res = self._client._http.get(
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

        res = self._client._http.get(
            url=f"https://{oauth_host}/app/v2/{PROJECT_CODE}/oauth/get_token",
            params={"data": json.dumps(data)},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        return res.json()
