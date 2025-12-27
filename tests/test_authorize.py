#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import unittest
import urllib.parse

cur_path = os.path.abspath(__file__)
parent = os.path.dirname
sys.path.insert(0, parent(parent(cur_path)))


from miloco_sdk import XiaomiClient



class TestXiaomiClient(unittest.TestCase):
    def test_gen_auth_url(self):
        client = XiaomiClient()
        redirect_uri="http://127.0.0.1:8000"
        redirect_uri=None

        # data = client.authorize.gen_auth_url(redirect_uri=redirect_uri, skip_confirm=False)
        # print(data)

    def test_get_code_url(self):
        client = XiaomiClient()
        code_url = client.authorize.get_code_url()
        url = urllib.parse.urlparse(code_url)
        query_params = urllib.parse.parse_qs(url.query)
        code = query_params["code"][0]
        # print(code)
        data = client.authorize.get_access_token_from_mico(code)
        print(data)


    # def test_get_access_token_from_mico(self):
    #     code = "C3_3EE74E3E817A0641CC68E2C0F1BAA5B7"
    #     client = XiaomiClient()
    #     data = client.authorize.get_access_token_from_mico(code)
    #     print(data)

    # def test_refresh_access_token_from_mico(self):
    #     refresh_token = "R3_10VPgr-qQLIyu-Sgmxx4Q3IRmHHQIBBax_2lHEe-04_vq6nJC0Bnag9-RZi02CFTpyhfy9Pu1570egeo8kf8Me2okFnZSpmsTMZdN0_7OZaJ3lKCPiO1M1InS1zQ1JU_3_EyMdO_dvMJsdrAGTIC4JIIqrKhYS0sbYB0fQxFjH8lfzmtw8Xv2mdJXcxy5i-eIvisScMjR1KbHSR6RVINuQ"
    #     client = XiaomiClient(OAUTH2_CLIENT_ID, device_uuid)
    #     data = client.authorize.refresh_access_token_from_mico(refresh_token)
    #     print(data)


if __name__ == "__main__":
    unittest.main()
