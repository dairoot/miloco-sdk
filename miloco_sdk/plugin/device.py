"""设备控制：开 / 关，以及通用的 MIoT 属性读写、动作调用。

小米设备的能力由 MIoT spec 描述（``urn:miot-spec-v2:device:outlet:...``），
开关就是某个服务下 access 含 ``write`` 的 ``on`` 属性。本模块按 spec 自动定位
主开关，所以不需要为每个型号写适配——``cuco.plug.v3``（米家智能插座）、灯、
风扇、空调等都走同一条路径。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from miloco_sdk.plugin.mijia import MijiaApi
from miloco_sdk.utils.error import MIoTError, MIoTErrorCode

logger = logging.getLogger(__name__)

SPEC_INSTANCE_URL: str = "https://miot-spec.org/miot-spec-v2/instance"
URN_BY_MODEL_URL: str = "https://miot-spec.org/internal/urn-by-model-version"
SPEC_HTTP_TIMEOUT: int = 10

# 设备主开关所在的服务：绝大多数设备是「与设备类型同名的服务」（灯是 light、风扇是
# fan、油烟机是 hood），插座 / 开关类是 switch。少数类型对不上，在此登记别名。
MAIN_SERVICE_ALIAS: Dict[str, str] = {
    "camera": "camera-control",
}

# 次要开关：这些服务下的 on 不是通断电。插座尤其典型——cuco.plug.v3 有 6 个可写的
# on（switch / indicator-light / charging-protection / quick-countdown /
# max-power-limit / over-use-ele-alert），只有 switch 那个才是通断电，误选会出现
# 「以为关了插座、其实只关了充电保护」。故主开关只认主服务，其余一律不自动选。
SECONDARY_SERVICES: set = {"indicator-light", "night-light", "ambient-light"}


def spec_type_name(urn: str) -> str:
    """取 spec urn 的类型名。

    ``urn:miot-spec-v2:service:switch:00007820:cuco-v3:1`` -> ``switch``
    ``urn:miot-spec-v2:property:on:00000006:cuco-v3:1``    -> ``on``
    """
    parts = urn.split(":")
    return parts[3] if len(parts) > 3 else ""


def resolve_switches(spec: Dict, urn: str) -> List[Dict]:
    """从 spec 里找出所有可写的 ``on`` 属性，并标记哪些是主开关。

    ``primary=True`` 表示位于设备主服务下（多键开关会有多个，每键一个）；
    ``primary=False`` 的是指示灯、倒计时、功率上限等功能开关，不代表设备通断电。
    """
    device_type = spec_type_name(urn)
    main_service = MAIN_SERVICE_ALIAS.get(device_type, device_type)

    switches: List[Dict] = []
    for service in spec.get("services", []) or []:
        service_name = spec_type_name(service.get("type", ""))
        for prop in service.get("properties", []) or []:
            if spec_type_name(prop.get("type", "")) != "on":
                continue
            if "write" not in (prop.get("access") or []):
                continue

            switches.append(
                {
                    "siid": service.get("iid"),
                    "piid": prop.get("iid"),
                    "service": service_name,
                    "description": service.get("description", "") or prop.get("description", ""),
                    "primary": service_name in ("switch", main_service),
                }
            )

    # 主开关在前；次要开关里指示灯这类排最后，方便调用方肉眼挑选
    switches.sort(key=lambda s: (not s["primary"], s["service"] in SECONDARY_SERVICES, s["siid"], s["piid"]))
    return switches


class Device(MijiaApi):
    """设备属性 / 动作接口。"""

    def __init__(self, client=None):
        super().__init__(client)
        # urn -> spec 实例；spec 是静态的，同一进程内只拉一次
        self._spec_cache: Dict[str, Dict] = {}
        # did -> (siid, piid)，避免每次开关都去解析 spec
        self._switch_cache: Dict[str, Tuple[int, int]] = {}

    # ── 通用属性 / 动作 ────────────────────────────────────────────────────

    def get_props(self, params: List[Dict]) -> List[Dict]:
        """批量读属性。params = [{"did": "xxx", "siid": 2, "piid": 1}]"""
        res_obj = self.api_request("/app/v2/miotspec/prop/get", {"datasource": 1, "params": params})
        if "result" not in res_obj:
            raise MIoTError(f"get props failed, {res_obj}", MIoTErrorCode.CODE_MIPS_INVALID_RESULT)
        return res_obj["result"]

    def set_props(self, params: List[Dict]) -> List[Dict]:
        """批量写属性。params = [{"did": "xxx", "siid": 2, "piid": 1, "value": True}]"""
        res_obj = self.api_request("/app/v2/miotspec/prop/set", {"params": params})
        if "result" not in res_obj:
            raise MIoTError(f"set props failed, {res_obj}", MIoTErrorCode.CODE_MIPS_INVALID_RESULT)
        return res_obj["result"]

    def get_prop(self, did: str, siid: int, piid: int) -> Any:
        """读单个属性值；设备离线或属性不可读时返回 None。"""
        results = self.get_props([{"did": did, "siid": siid, "piid": piid}])
        if not results:
            return None
        return results[0].get("value", None)

    def set_prop(self, did: str, siid: int, piid: int, value: Any) -> Dict:
        """写单个属性。下发失败（设备离线、参数非法等）抛 :class:`MIoTError`。"""
        results = self.set_props([{"did": did, "siid": siid, "piid": piid, "value": value}])
        if not results:
            raise MIoTError(
                f"set prop failed, empty result, {did}.{siid}.{piid}", MIoTErrorCode.CODE_MIPS_INVALID_RESULT
            )

        result = results[0]
        if result.get("code", 0) != 0:
            raise MIoTError(
                f"set prop failed, {did}.{siid}.{piid}={value}, code={result.get('code')}",
                MIoTErrorCode.CODE_UNAVAILABLE,
            )
        return result

    def call_action(self, did: str, siid: int, aiid: int, in_: Optional[List[Any]] = None) -> Dict:
        """调用动作。``in_`` 按 spec 的入参顺序传值。"""
        params = {"did": did, "siid": siid, "aiid": aiid, "in": in_ or []}
        res_obj = self.api_request("/app/v2/miotspec/action", {"params": params})
        if "result" not in res_obj:
            raise MIoTError(f"call action failed, {res_obj}", MIoTErrorCode.CODE_MIPS_INVALID_RESULT)
        return res_obj["result"]

    # ── 开关 ──────────────────────────────────────────────────────────────

    def get_power(self, did: str, siid: Optional[int] = None, piid: Optional[int] = None) -> Optional[bool]:
        """查询设备当前是开还是关。返回 True(开) / False(关)；读不到返回 None。"""
        if siid is None or piid is None:
            siid, piid = self.find_switch_iid(did)
        value = self.get_prop(did, siid, piid)
        return None if value is None else bool(value)

    def set_power(self, did: str, on: bool, siid: Optional[int] = None, piid: Optional[int] = None) -> Dict:
        """控制设备开 / 关。

        ``siid`` / ``piid`` 不传时按 spec 自动定位主开关；多路开关（多键墙壁开关等）
        想指定某一路时显式传入，可用 :meth:`find_switch_list` 查看全部可控开关。
        """
        if siid is None or piid is None:
            siid, piid = self.find_switch_iid(did)
        logger.info("set power, did=%s, %s.%s=%s", did, siid, piid, on)
        return self.set_prop(did, siid, piid, bool(on))

    def turn_on(self, did: str, siid: Optional[int] = None, piid: Optional[int] = None) -> Dict:
        """打开设备。"""
        return self.set_power(did, True, siid=siid, piid=piid)

    def turn_off(self, did: str, siid: Optional[int] = None, piid: Optional[int] = None) -> Dict:
        """关闭设备。"""
        return self.set_power(did, False, siid=siid, piid=piid)

    def toggle(self, did: str, siid: Optional[int] = None, piid: Optional[int] = None) -> Dict:
        """反转设备开关状态（先读后写）。"""
        if siid is None or piid is None:
            siid, piid = self.find_switch_iid(did)
        current = self.get_power(did, siid=siid, piid=piid)
        if current is None:
            raise MIoTError(
                f"toggle failed, 读不到当前开关状态（设备可能离线），did={did}", MIoTErrorCode.CODE_UNAVAILABLE
            )
        return self.set_power(did, not current, siid=siid, piid=piid)

    # ── spec 解析 ─────────────────────────────────────────────────────────

    def get_device_info(self, did: str) -> Dict:
        """按 did 取设备信息（含 ``model`` / ``spec_type`` / ``isOnline``）。"""
        res_obj = self._client.home.get_device_list_by_did([did])
        devices = (res_obj.get("result") or {}).get("list") or []
        for device in devices:
            if device.get("did") == did:
                return device
        raise MIoTError(f"设备不存在或无权限访问，did={did}", MIoTErrorCode.CODE_INVALID_PARAMS)

    def get_device_urn(self, did: str) -> str:
        """取设备的 spec urn；设备信息里没有 ``spec_type`` 时按 model 反查。"""
        device = self.get_device_info(did)
        urn = device.get("spec_type", None)
        if urn:
            return urn

        model = device.get("model", None)
        if not model:
            raise MIoTError(f"设备缺少 model 字段，无法定位 spec，did={did}", MIoTErrorCode.CODE_SPEC_DEFAULT)

        http_res = self._client._http.get(
            url=URN_BY_MODEL_URL, params={"model": model, "version": 0}, timeout=SPEC_HTTP_TIMEOUT
        )
        if http_res.status_code != 200:
            raise MIoTError(
                f"get urn by model failed, {http_res.status_code}, {model}", MIoTErrorCode.CODE_SPEC_DEFAULT
            )
        urn = (http_res.json() or {}).get("urn", None)
        if not urn:
            raise MIoTError(f"未找到 model={model} 对应的 spec urn", MIoTErrorCode.CODE_SPEC_DEFAULT)
        return urn

    def get_spec(self, urn: str) -> Dict:
        """拉取 spec 实例（服务 / 属性 / 动作定义），按 urn 缓存。"""
        if urn in self._spec_cache:
            return self._spec_cache[urn]

        http_res = self._client._http.get(url=SPEC_INSTANCE_URL, params={"type": urn}, timeout=SPEC_HTTP_TIMEOUT)
        if http_res.status_code != 200:
            raise MIoTError(f"get spec failed, {http_res.status_code}, {urn}", MIoTErrorCode.CODE_SPEC_DEFAULT)

        spec: Dict = http_res.json()
        self._spec_cache[urn] = spec
        return spec

    def find_switch_list(self, did: str) -> List[Dict]:
        """列出设备所有可写的 ``on`` 属性（即所有可控开关），主开关在前。

        返回 ``[{"siid", "piid", "service", "description", "primary"}, ...]``。
        多键开关会有多个 ``primary``；插座除主开关外还有指示灯等功能开关
        （``primary=False``，不代表通断电）。
        """
        urn = self.get_device_urn(did)
        return resolve_switches(self.get_spec(urn), urn)

    def find_switch_iid(self, did: str) -> Tuple[int, int]:
        """定位设备主开关的 ``(siid, piid)``，按 did 缓存。

        只认主服务下的开关：定位不到时直接报错并列出候选，交由调用方显式指定
        ``siid`` / ``piid``——宁可报错，也不能把「倒计时开关」当成设备总开关去关。
        """
        if did in self._switch_cache:
            return self._switch_cache[did]

        switches = self.find_switch_list(did)
        primary = [s for s in switches if s["primary"]]

        if not primary:
            hint = ", ".join(f"{s['siid']}.{s['piid']}({s['service']})" for s in switches) or "无"
            raise MIoTError(
                f"未能定位主开关，did={did}。可写的 on 属性: {hint}。"
                f"若确认其中某个是总开关，请显式传入 siid / piid，如 turn_on(did, siid=2, piid=1)",
                MIoTErrorCode.CODE_UNAVAILABLE,
            )

        switch = primary[0]
        if len(primary) > 1:
            logger.info("设备 %s 有 %d 路主开关，默认使用第一路 %s", did, len(primary), switch)

        iid = (switch["siid"], switch["piid"])
        self._switch_cache[did] = iid
        return iid
