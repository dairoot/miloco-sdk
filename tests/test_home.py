#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import unittest

cur_path = os.path.abspath(__file__)
parent = os.path.dirname
sys.path.insert(0, parent(parent(cur_path)))

from miloco_sdk import XiaomiClient

access_token = os.getenv("ACCESS_TOKEN")

if not access_token:
    raise ValueError("ACCESS_TOKEN is not set")

class TestXiaomiClient(unittest.TestCase):
    
    def test_get_home_list(self):
        client = XiaomiClient(access_token=access_token)
        data = client.home.get_home_list()
        print(data)

    def test_get_device_list(self):
        client = XiaomiClient(access_token=access_token)
        data = client.home.get_device_list()
        for line in data:
            print(line)


if __name__ == "__main__":
    unittest.main()
