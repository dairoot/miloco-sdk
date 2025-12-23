import base64
import json
import os
from typing import Any, Dict, Optional

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from miloco_sdk.base import BaseApi
from miloco_sdk.utils.const import (
    MIHOME_HTTP_API_PUBKEY,
    MIHOME_HTTP_API_TIMEOUT,
    MIHOME_HTTP_USER_AGENT,
    MIHOME_HTTP_X_CLIENT_BIZID,
    MIHOME_HTTP_X_ENCRYPT_TYPE,
)

OAUTH2_CLIENT_ID: str = "2882303761520431603"


PROJECT_CODE: str = "mico"


class Home(BaseApi):

    def __init__(self, client=None):
        self._client = client
        self._random_aes_key = os.urandom(16)

        self._base_url = f"https://{PROJECT_CODE}.api.mijia.tech"

        self._cipher = Cipher(
            algorithms.AES(self._random_aes_key), modes.CBC(self._random_aes_key), backend=default_backend()
        )

        self._client_secret_b64 = base64.b64encode(
            load_pem_public_key(MIHOME_HTTP_API_PUBKEY.encode("utf-8"), default_backend()).encrypt(
                plaintext=self._random_aes_key, padding=asym_padding.PKCS1v15()
            )
        ).decode(
            "utf-8"
        )  # type: ignore

    @property
    def __api_request_headers(self) -> Dict:

        return {
            "Content-Type": "text/plain",
            "User-Agent": MIHOME_HTTP_USER_AGENT,
            "X-Client-BizId": MIHOME_HTTP_X_CLIENT_BIZID,
            "X-Encrypt-Type": MIHOME_HTTP_X_ENCRYPT_TYPE,
            "X-Client-AppId": OAUTH2_CLIENT_ID,
            "X-Client-Secret": self._client_secret_b64,
            "Host": "mico.api.mijia.tech",
            "Authorization": f"Bearer{self._client._access_token}",
        }

    def aes_encrypt_with_b64(self, data: Dict) -> str:
        """AES encrypt."""
        encryptor = self._cipher.encryptor()
        padder = sym_padding.PKCS7(128).padder()
        padded_data = padder.update(json.dumps(data).encode("utf-8")) + padder.finalize()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        result = base64.b64encode(encrypted).decode("utf-8")
        return result

    def aes_decrypt_with_b64(self, data: str) -> Dict:
        """AES decrypt."""
        decryptor = self._cipher.decryptor()
        unpadder = sym_padding.PKCS7(128).unpadder()
        decrypted = decryptor.update(base64.b64decode(data)) + decryptor.finalize()
        unpadded_data = unpadder.update(decrypted) + unpadder.finalize()
        result = json.loads(unpadded_data.decode("utf-8"))
        return result

    def api_request(self, url_path: str, data: Dict):
        self._base_url = f"https://{PROJECT_CODE}.api.mijia.tech"

        http_res = self._client._http.post(
            url=f"{self._base_url}{url_path}",
            data=self.aes_encrypt_with_b64(data),
            headers=self.__api_request_headers,
        )
        res_obj: Dict = self.aes_decrypt_with_b64(http_res.text)
        return res_obj

    def get_home_list(self):
        url_path = "/app/v2/homeroom/gethome"

        data = {
            "limit": 150,
            "fetch_share": False,
            "fetch_share_dev": False,
            "plat_form": 0,
            "app_ver": 9,
        }
        return self.api_request(url_path, data)

    def get_device_list_by_did(self, dids: list[str]):
        data: Dict = {"limit": 200, "get_split_device": True, "dids": dids}
        url_path = "/app/v2/home/device_list_page"

        return self.api_request(url_path, data)

    def get_device_list(self):
        result = []
        home_data = self.get_home_list()
        for line in home_data["result"]["homelist"]:
            for room in line["roomlist"]:
                if not room["dids"]:
                    continue
                # print(room)
                room_info = {
                    "room_id": room["id"],
                    "room_name": room["name"],
                }
                device_list = self.get_device_list_by_did(room["dids"])
                for device_info in device_list["result"]["list"]:
                    device_info.update(room_info)
                    # print(device_info)
                    result.append(device_info)
        return sorted(result, key=lambda x: x.get("did", ""))
