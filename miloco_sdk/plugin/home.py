from typing import Dict

from miloco_sdk.plugin.mijia import MijiaApi


class Home(MijiaApi):

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
