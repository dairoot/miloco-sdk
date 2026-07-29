import base64
import json
import os
from typing import Dict

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from miloco_sdk.base import BaseApi
from miloco_sdk.utils.const import (
    MIHOME_HTTP_API_PUBKEY,
    MIHOME_HTTP_USER_AGENT,
    MIHOME_HTTP_X_CLIENT_BIZID,
    MIHOME_HTTP_X_ENCRYPT_TYPE,
)

OAUTH2_CLIENT_ID: str = "2882303761520431603"

PROJECT_CODE: str = "mico"


class MijiaApi(BaseApi):
    """米家加密 HTTP 接口基类。

    请求体 AES-CBC 加密后以 text/plain 发出，AES key 用服务端公钥 RSA 加密放在
    ``X-Client-Secret`` 头里；响应体同样是 AES 密文。子类（``Home`` / ``Device``）
    只负责拼 ``url_path`` 和业务参数，加解密统一走 :meth:`api_request`。
    """

    def __init__(self, client=None):
        super().__init__(client)
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
    def _api_request_headers(self) -> Dict:

        return {
            "Content-Type": "text/plain",
            "User-Agent": MIHOME_HTTP_USER_AGENT,
            "X-Client-BizId": MIHOME_HTTP_X_CLIENT_BIZID,
            "X-Encrypt-Type": MIHOME_HTTP_X_ENCRYPT_TYPE,
            "X-Client-AppId": OAUTH2_CLIENT_ID,
            "X-Client-Secret": self._client_secret_b64,
            "Host": f"{PROJECT_CODE}.api.mijia.tech",
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

    def api_request(self, url_path: str, data: Dict) -> Dict:
        http_res = self._client._http.post(
            url=f"{self._base_url}{url_path}",
            data=self.aes_encrypt_with_b64(data),
            headers=self._api_request_headers,
        )
        if http_res.status_code != 200:
            raise Exception(f"invalid response code, {http_res.status_code}, {http_res.text}")

        res_obj: Dict = self.aes_decrypt_with_b64(http_res.text)
        return res_obj
