#!/usr/bin/env python3
"""海信 AIoT 设备控制脚本（本地直连海信云端，不经过微信小程序）

只用 Python 标准库，不需要 pip 安装任何东西。

能力对齐原「海信爱家小程序技能包」：
  家庭：列表、切换当前家庭
  设备：列表（按家庭/品类/房间）、详情、功能视图（物模型能力）
  控制：白电/电视走海信对话服务（传用户原话，由海信解析执行）、物模型精确下发
  查询：状态快照、自然语言问答

------------------------------------------------------------------
只有一个域名：https://iot-aihome.hismarttv.com
------------------------------------------------------------------
1) App 侧接口  https://iot-aihome.hismarttv.com/4.0/iot/...
   家庭、设备详情、功能视图、物模型下发。

2) 对话服务    https://iot-aihome.hismarttv.com/4.0/iot/agent/iot/app/chat
   控制与状态问答走这条，把用户原话交给海信云端解析执行。

两套接口的网关凭证（appKey / appSecret / 签名）和用户身份（accessToken / customerId）
都由 Sandbox NetworkPolicy 托管注入。本脚本只请求上面这些原始业务地址，
不读取、不保存、不发送任何 Token/Key，也不做 OAuth。

------------------------------------------------------------------
环境变量
------------------------------------------------------------------
HISENSE_DATA_DIR      本用户的持久化目录，默认 /data/user/hisense-smart-home-assistant
HISENSE_SESSION_ID    本轮对话 id，有则用来界定会话边界（可选）

两个都不是凭证。用户隔离靠 HISENSE_DATA_DIR 这个按用户挂载的目录，
不靠模型传 id；目录里只有家庭上下文和会话 sid。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# ===== 凭证 =====
# 海信网关凭证（appKey / appSecret / X-Sign-For 签名）由 Sandbox NetworkPolicy 托管注入。
# 本脚本只请求下面这些原始业务地址，不读取、不保存、不发送任何 Token/Key，也不算签名。

# ===== 域名（只有一个，与小程序技能包一致，不做成环境变量）=====
AIOT_HOST = "https://iot-aihome.hismarttv.com"
CHAT_HOST = "https://iot-aihome.hismarttv.com"

# ===== App 侧接口路径 =====
APP_API = {
    "HOME_LIST": "/4.0/iot/home/list",
    "HOME_SET_CURRENT": "/4.0/iot/home/set_current",
    "DEVICE_LIST": "/4.0/iot/devices/list",
    "DEVICE_DETAIL": "/4.0/iot/devices/detail",
    "DEVICE_FUNCTIONS": "/4.0/iot/devices/function/getByProduct",
    "DEVICE_EXECUTE": "/4.0/iot/devices/execute",
}
APP_VERSION = "1.5.2.0"
APP_TYPE = 2          # 1=安卓 2=其它；connector 侧固定走非安卓
SOURCE_TYPE = 21
SOURCE_TYPE_DEVICE_LIST = 20
SOURCE_NAME = "hisense-skill"
DEFAULT_PARTNER_ID = "1001"

# ===== 对话服务 =====
PATH_CHAT = "/4.0/iot/agent/iot/app/chat"
DOMAIN_HOME = "SMART_HOME_CONTROL"    # 白电：空调/冰箱/洗衣机/干衣机
DOMAIN_TV = "CONTROL"                 # 电视
CHAT_TERMINAL = 7                     # 7=微信AI
CHAT_APP_VERSION = "7.0.0.4"

PAYLOAD_VERSION = "1.0"
SUCCESS_STATUS = "SUCCESS"
TIMEOUT = 60

# ===== 用户态存储 =====
# 隔离靠宿主按用户挂载的目录，不靠模型传 id，也不写 ~ 下的全局单文件。
# 只存家庭上下文和会话 sid，不存登录态。
STATE_DIR_ENV = "HISENSE_DATA_DIR"
DEFAULT_STATE_DIR = "/data/user/hisense-smart-home-assistant"
STATE_SCHEMA_VERSION = 1
# 同一 domain 的 sid 复用窗口：超过这么久没说话就当新会话，
# 免得把几小时前的上下文带给上游，让「再高点」接到错的那一轮。
SID_TTL_SECONDS = 30 * 60

CATEGORY_BY_NAME = [
    (("干衣机", "烘干机"), "connector.device.type.dryer"),
    (("洗衣机",), "connector.device.type.washer"),
    (("电视",), "connector.device.type.TV"),
    (("空调",), "connector.device.type.aircondition"),
    (("冰箱",), "connector.device.type.fridge"),
]
# 对话服务返回这些话 = 当前家庭下没有这台设备
NO_DEVICE_PATTERNS = (
    "没有找到对应设备", "当前家庭下没有找到", "当前家庭下没有",
    "未找到对应设备", "没有找到设备",
)

EXIT_USAGE = 2
EXIT_RUNTIME = 1


class HisenseError(Exception):
    def __init__(self, message, code=""):
        self.code = code
        super().__init__(message)


# ---------------- 基础 ----------------

# 凭证由沙箱代理注入，脚本这边无从校验。出现签名/appKey 类报错一律意味着
# 请求没经过代理，或者代理没给这个域名配凭证 —— 不是脚本能修的，指向部署。
_PROXY_MISS = "（请求没拿到网关凭证：确认沙箱 NetworkPolicy 给 iot-aihome.hismarttv.com 配了凭证注入。可跑 diag 复现）"


def _hint(text):
    t = text or ""
    if re.search(r"no x-sign-for|no signature found|wrong signature|signature|invalid appkey|appkey|签名", t, re.I):
        return _PROXY_MISS
    return ""


def _http(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise HisenseError(_with_hint(f"HTTP {e.code} {raw[:300]}"))
    except urllib.error.URLError as e:
        raise HisenseError(f"网络请求失败：{e.reason}")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HisenseError(f"响应不是合法 JSON：{raw[:300]}")


def _with_hint(msg):
    h = _hint(msg)
    return f"{msg} {h}".strip() if h else msg


# ---------------- App 侧接口 ----------------

def _post_app(path, payload):
    """App 侧 AIoT 接口：走 iot-aihome 网关。

    accessToken 与 payload.customerId 由沙箱代理注入，这里不组装。
    """
    ms = int(time.time() * 1000)
    body_obj = {
        "_t": ms,
        "deviceId": "",
        "header": {
            "messageId": f"skill-{ms}-{uuid.uuid4().hex[:8]}",
            "timestamp": ms,
            "languageId": 0,
        },
        "appVersion": APP_VERSION,
        "appType": APP_TYPE,
        "payload": payload,
    }
    body = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
    res = _http(AIOT_HOST + path, data=body.encode("utf-8"), headers={
        "Content-Type": "application/json",
    })
    top = str(res.get("resultCode", "")) if res.get("resultCode") is not None else ""
    if top and top not in ("0", "200"):
        raise HisenseError(_with_hint(f"海信接口返回失败 [{path}] code={top}: {res.get('errorDesc') or ''}"), top)
    pay = res.get("payload") or {}
    if pay and pay.get("status") and pay.get("status") != SUCCESS_STATUS:
        desc = str(pay.get("errorDesc") or pay.get("errorMsg") or "")
        raise HisenseError(_with_hint(f"海信接口返回失败 [{path}]: {desc}"))
    return pay


# ---------------- 对话服务 ----------------

def call_chat(query, domain, device_id="", category_code=""):
    """对话服务：accessToken 与 payload.customerId 由沙箱代理注入，这里不组装。"""
    body = {
        "header": {
            "messageId": f"{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}",
            "timestamp": str(int(time.time() * 1000)),
            "languageId": 1,
        },
        "payload": {
            "query": query,
            "sid": get_or_create_sid(domain),
            "terminalDeviceId": "",
            "newConversation": "0",
            "deepSeek": "0",
            "domain": domain,
            "additional": {
                "home": {"id": ensure_current_home()[0], "provinceCode": ""},
                "device": {"partnerId": "", "id": device_id or "", "featureCode": "",
                           "wifiId": "", "sn": "", "categoryCode": category_code or "", "productCode": ""},
            },
        },
        "appVersion": CHAT_APP_VERSION,
        "terminal": CHAT_TERMINAL,
        "payloadVersion": PAYLOAD_VERSION,
    }
    body_str = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    res = _http(CHAT_HOST + PATH_CHAT, data=body_str.encode("utf-8"), headers={
        "Content-Type": "application/json;charset=UTF-8",
    })
    top = str(res.get("resultCode", "")) if res.get("resultCode") is not None else ""
    if top and top not in ("0", "200"):
        raise HisenseError(_with_hint(f"海信对话服务返回失败 code={top}: {res.get('errorDesc') or ''}"), top)
    pay = res.get("payload") or {}
    err = pay.get("errorCode")
    if err not in (None, "", "0", 0):
        raise HisenseError(_with_hint(f"海信对话服务返回错误：{pay.get('errorDesc') or err}"))
    text = extract_text(pay)
    devices = collect_devices(pay)
    # 当前家庭没有这台设备 → 提示它在哪个家庭（只提示，不自动切换）
    if any(p in text for p in NO_DEVICE_PATTERNS):
        fallback = no_device_hint(query)
        if fallback:
            return {"text": fallback, "devices": devices, "noDeviceInCurrentHome": True}
    return {"text": text, "devices": devices}


def extract_text(pay):
    out = []
    for item in (pay.get("data") or []):
        msg = (item or {}).get("msg") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            out.append(re.sub(r"[（(]\s*[a-zA-Z_][a-zA-Z0-9_]*\s*:\s*[a-zA-Z0-9_-]+\s*[)）]", "", content.strip()))
    return "".join(out)


def collect_devices(pay):
    out = []
    for item in (pay.get("data") or []):
        for d in ((item or {}).get("displayDeviceInfo") or []):
            if isinstance(d, dict):
                out.append({k: v for k, v in d.items() if k != "states"})
    return out


def no_device_hint(query):
    """当前家庭没有该设备时，查全部家庭，告诉用户它在哪个家庭"""
    cat = category_code_of(query)
    if not cat:
        return ""
    try:
        pay = _post_app(APP_API["DEVICE_LIST"], {
            "sourceType": SOURCE_TYPE_DEVICE_LIST,
            "bindStatus": 0,
            "withState": True,
        })
        matched = [d for d in (pay.get("devices") or []) if d.get("categoryCode") == cat]
        if not matched:
            return ""
        home_ids = []
        for d in matched:
            hid = (d.get("bindInfo") or {}).get("homeId") or d.get("homeId") or ""
            if hid and hid not in home_ids:
                home_ids.append(hid)
        if not home_ids:
            return ""
        names = resolve_home_names(home_ids)
        if not names:
            return ""
        label = category_label(cat)
        if len(names) == 1:
            return f"{label}在「{names[0]}」家庭下，请切换到该家庭后再控制。"
        return f"{label}在以下家庭下：{'、'.join('「' + n + '」' for n in names)}，请切换到对应家庭后再控制。"
    except HisenseError:
        return ""


def resolve_home_names(home_ids):
    try:
        pay = _post_app(APP_API["HOME_LIST"], {"sourceType": SOURCE_TYPE})
    except HisenseError:
        return []
    homes = pay.get("homes") or []
    return [h.get("name") for h in homes if h.get("id") in home_ids and h.get("name")]


# ---------------- 身份 / 家庭 ----------------

def data_dir():
    return os.environ.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR


def state_path():
    return os.path.join(data_dir(), "state.json")


def _empty_state():
    return {"schema_version": STATE_SCHEMA_VERSION,
            "currentHomeId": "", "homes": [], "sids": {}}


def _load_state():
    """读当前用户的状态。文件缺失、损坏、schema 不认都退回空状态。

    这里不做归属校验：用户隔离由宿主挂载的 HISENSE_DATA_DIR 保证，
    脚本已经拿不到用户 id 了，也不该拿。
    """
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA_VERSION:
        return _empty_state()
    return {**_empty_state(), **state}


def _save_state(state):
    """原子写：先写同目录临时文件再 rename，中断或并发不会留下半个文件。

    写失败只降级（下次重新查接口），不打断当前命令。
    """
    payload = {**state, "schema_version": STATE_SCHEMA_VERSION}
    path = state_path()
    staging = ""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        staging = f"{path}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
        with open(staging, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(staging, path)
    except OSError:
        if staging:
            try:
                os.unlink(staging)
            except OSError:
                pass
    return payload


# ---------------- 会话 ----------------

def get_or_create_sid(domain):
    """同一 domain 复用 sid，让「再高点」「风小点」这类相对指令在上游续得上上一轮。

    小程序侧把 sid 放在分包内存里（sessionMap），CLI 每次都是新进程，只能落盘。
    宿主给了会话 id 就跟着它走，没给就按空闲时长过期。
    """
    key = domain or "__default__"
    now = int(time.time())
    host_session = os.environ.get("HISENSE_SESSION_ID") or ""
    state = _load_state()
    entry = (state.get("sids") or {}).get(key) or {}
    try:
        idle = now - int(entry.get("ts") or 0)
    except (TypeError, ValueError):
        idle = SID_TTL_SECONDS + 1
    sid = entry.get("sid") or ""
    if not (sid and entry.get("session") == host_session and idle <= SID_TTL_SECONDS):
        sid = f"yb_{key}_{host_session or uuid.uuid4().hex[:12]}"
    sids = dict(state.get("sids") or {})
    sids[key] = {"sid": sid, "ts": now, "session": host_session}
    _save_state({**state, "sids": sids})
    return sid


# ---------------- 家庭上下文 ----------------

def _match_home(homes, wanted):
    """先按 id，再按名字精确匹配，最后才互相包含 —— 精确匹配必须赢过子串匹配。"""
    for h in homes:
        if h.get("id") == wanted:
            return h
    for h in homes:
        if (h.get("name") or "") == wanted:
            return h
    for h in homes:
        name = h.get("name") or ""
        if name and (wanted in name or name in wanted):
            return h
    return None


def fetch_homes():
    """拉家庭列表，返回 (homes, 后端认为的当前家庭 id)，并把列表落盘备查。"""
    pay = _post_app(APP_API["HOME_LIST"], {"sourceType": SOURCE_TYPE})
    homes = pay.get("homes") or []
    slim = [{"id": h.get("id"), "name": h.get("name")} for h in homes if h.get("id")]
    _save_state({**_load_state(), "homes": slim})
    return homes, (pay.get("currentHomeId") or "")


def home_name_of(home_id):
    for h in (_load_state().get("homes") or []):
        if h.get("id") == home_id:
            return h.get("name") or ""
    return ""


def remember_current_home(home_id, homes=None):
    state = _load_state()
    patch = {"currentHomeId": home_id}
    if homes is not None:
        patch["homes"] = [{"id": h.get("id"), "name": h.get("name")}
                          for h in homes if h.get("id")]
    _save_state({**state, **patch})


def ensure_current_home():
    """取当前家庭 (id, name)：缓存优先，缺失就查一次 home/list 再回写。

    一个家庭都没有时直接报错。不能静默返回空串——那样 devices 不带 homeId，
    海信会把所有家庭的设备都返回来，用户和模型都察觉不到。
    """
    state = _load_state()
    home_id = state.get("currentHomeId") or ""
    if home_id:
        return home_id, home_name_of(home_id)
    homes, current = fetch_homes()
    home_id = current or (homes[0].get("id") if homes else "")
    if not home_id:
        raise HisenseError("当前账号下没有可用的家庭，请先在海信爱家 App 里创建或加入一个家庭。")
    remember_current_home(home_id, homes)
    return home_id, home_name_of(home_id)


def category_code_of(text):
    if not text:
        return ""
    for names, code in CATEGORY_BY_NAME:
        if any(n in text for n in names):
            return code
    return ""


def category_label(code):
    for names, c in CATEGORY_BY_NAME:
        if c == code:
            return names[0]
    return "该设备"


# ---------------- 命令 ----------------

def cmd_homes(args):
    homes, current = fetch_homes()
    cur = current or _load_state().get("currentHomeId") or (homes[0].get("id") if homes else "")
    if cur:
        remember_current_home(cur, homes)
    return {"currentHomeId": cur, "count": len(homes),
            "homes": [{"id": h.get("id"), "name": h.get("name")} for h in homes]}


def cmd_switch_home(args):
    homes, _ = fetch_homes()
    target = _match_home(homes, args.name_or_id)
    if not target:
        raise HisenseError(f"没有找到名为「{args.name_or_id}」的家庭，可先用 homes 看看有哪些家庭。")
    _post_app(APP_API["HOME_SET_CURRENT"], {"sourceType": SOURCE_TYPE,
                                            "homeId": target.get("id")})
    remember_current_home(target.get("id"), homes)
    return {"switched": True, "homeId": target.get("id"), "homeName": target.get("name")}


def cmd_devices(args):
    cat = category_code_of(args.category)
    if args.home:
        homes, _ = fetch_homes()
        target = _match_home(homes, args.home)
        if not target:
            raise HisenseError(f"没有找到名为「{args.home}」的家庭")
        home_id, home_name = target.get("id"), target.get("name") or ""
    else:
        home_id, home_name = ensure_current_home()

    # homeId 必传：不传的话海信会返回所有家庭的设备
    pay = _post_app(APP_API["DEVICE_LIST"], {
        "sourceType": SOURCE_TYPE_DEVICE_LIST,
        "homeId": home_id, "bindStatus": 0, "withState": True,
    })
    devices = pay.get("devices") or []

    def name_of(d):
        return str(d.get("nickname") or d.get("deviceName") or "")

    if cat:
        devices = [d for d in devices if d.get("categoryCode") == cat]
    if args.room:
        devices = [d for d in devices if args.room in name_of(d)]
    if args.name:
        devices = [d for d in devices if args.name in name_of(d)]
    return {
        "homeId": home_id, "homeName": home_name, "count": len(devices),
        "devices": [{"deviceId": d.get("deviceId"), "nickname": name_of(d) or "未命名设备",
                     "categoryCode": d.get("categoryCode"),
                     "onlineStatus": d.get("onlineStatus", d.get("online", ""))} for d in devices],
    }


def cmd_detail(args):
    pay = _post_app(APP_API["DEVICE_DETAIL"], {"sourceType": SOURCE_TYPE,
                                               "deviceId": args.device_id,
                                               "partnerId": DEFAULT_PARTNER_ID})
    return {"device": pay.get("device") or pay}


def cmd_functions(args):
    pay = _post_app(APP_API["DEVICE_FUNCTIONS"], {
        "sourceType": SOURCE_TYPE,
        "products": [{"productCode": args.product or "", "categoryCode": args.category or "",
                      "deviceId": args.device_id, "partnerId": DEFAULT_PARTNER_ID}],
    })
    return {"products": pay.get("products") or pay}


def cmd_exec(args):
    try:
        actions = json.loads(args.actions_json)
    except json.JSONDecodeError:
        raise HisenseError("actions 必须是 JSON 数组，例如 '[{\"code\":\"powerStatus\",\"value\":\"1\"}]'", "USAGE")
    if not isinstance(actions, list):
        raise HisenseError("actions 必须是数组", "USAGE")
    pay = _post_app(APP_API["DEVICE_EXECUTE"], {
        "sourceType": SOURCE_TYPE, "sourceName": SOURCE_NAME,
        "deviceId": args.device_id, "partnerId": DEFAULT_PARTNER_ID, "actions": actions,
    })
    return {"states": pay.get("aiotStates") or pay.get("states") or pay}


def cmd_status(args):
    if args.query:
        return call_chat(args.query, DOMAIN_HOME)
    if not args.device_ids:
        raise HisenseError("status 需要 --query 或至少一个 deviceId", "USAGE")
    out = []
    for did in args.device_ids:
        pay = _post_app(APP_API["DEVICE_DETAIL"], {"sourceType": SOURCE_TYPE,
                                                   "deviceId": did,
                                                   "partnerId": DEFAULT_PARTNER_ID})
        dev = pay.get("device") or pay
        if dev:
            out.append(dev)
    return {"devices": out}


def cmd_control(args):
    return call_chat(args.query, DOMAIN_HOME, args.device, category_code_of(args.category))


def cmd_tv(args):
    return call_chat(args.query, DOMAIN_TV, args.device, "connector.device.type.TV")


# ---------------- 自检 ----------------

def _raw_post(url, body_str, headers, timeout=20):
    """不抛异常的原始请求，返回 (status, text)"""
    req = urllib.request.Request(url, data=body_str.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                   # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def cmd_diag(args):
    """一键自检：判断请求有没有拿到沙箱代理注入的网关凭证。

    脚本自己不带任何 appKey / 签名，所以返回只有两种可能：
      仍是 No X-Sign-For Header / Invalid appKey 之类 → 请求没经过代理，或者代理
        没给这个域名配凭证，问题在部署，不在脚本；
      换成业务报错（accessToken 类）或正常回包 → 凭证已注入，网关这层是通的。
    """
    ms = int(time.time() * 1000)
    body = json.dumps({"_t": ms, "deviceId": "diag",
                       "header": {"messageId": f"diag-{ms}", "timestamp": ms, "languageId": 0},
                       "appVersion": APP_VERSION, "appType": APP_TYPE, "payload": {}},
                      ensure_ascii=False, separators=(",", ":"))

    def brief(t):
        try:
            d = json.loads(t)
        except json.JSONDecodeError:
            return t[:120]
        return str(d.get("errorDesc") or d.get("error") or d.get("message") or t)[:160]

    items = []
    injected = []
    for name, url in (("App 侧网关", AIOT_HOST + APP_API["HOME_LIST"]),
                      ("对话服务", CHAT_HOST + PATH_CHAT)):
        status, text = _raw_post(url, body, {"Content-Type": "application/json;charset=UTF-8"})
        desc = brief(text)
        if status in (-1, 0):
            verdict, ok = "网络不通", False
        elif re.search(r"no x-sign-for|no signature found|wrong signature|invalid appkey|appkey",
                       desc, re.I):
            verdict, ok = "代理未注入凭证（网关仍在要签名/appKey）", False
        else:
            verdict, ok = "凭证已注入，网关放行（看具体返回）", True
        injected.append(ok)
        items.append({"gateway": name, "url": url,
                      "返回": f"HTTP {status} {desc}", "结论": verdict})

    if all(injected):
        conclusion = "沙箱代理已为两个入口注入凭证，可以开始调 homes / devices / control。"
    elif not any(injected):
        hosts = "、".join(dict.fromkeys(urllib.parse.urlparse(i["url"]).netloc for i in items))
        conclusion = (f"两个入口都没拿到凭证：确认沙箱 NetworkPolicy 给 {hosts} 配了海信网关的 "
                      "appKey / appSecret 注入，且脚本出网确实走了代理。")
    else:
        bad = "、".join(i["gateway"] for i, ok in zip(items, injected) if not ok)
        conclusion = f"只有部分入口拿到凭证（缺：{bad}）：代理的路径匹配可能没覆盖全，需要补齐。"

    return {"credentials": "由 Sandbox NetworkPolicy 注入", "gateways": items,
            "conclusion": conclusion}


# ---------------- CLI ----------------

def build_parser():
    import argparse
    p = argparse.ArgumentParser(prog="hisense_api.py", description="海信 AIoT 设备控制")
    sub = p.add_subparsers(dest="command", required=True)

    h = sub.add_parser("homes", help="家庭列表 / 当前家庭")
    h.set_defaults(func=cmd_homes)

    sh = sub.add_parser("switch-home", help="切换当前家庭")
    sh.add_argument("name_or_id")
    sh.set_defaults(func=cmd_switch_home)

    d = sub.add_parser("devices", help="设备列表")
    d.add_argument("--home", default="", help="家庭名，不传用当前家庭")
    d.add_argument("--category", default="", help="空调/电视/冰箱/洗衣机/干衣机")
    d.add_argument("--room", default="", help="按设备名里的房间词过滤，如 客厅")
    d.add_argument("--name", default="", help="按昵称过滤")
    d.set_defaults(func=cmd_devices)

    det = sub.add_parser("detail", help="设备详情（含运行状态）")
    det.add_argument("device_id")
    det.set_defaults(func=cmd_detail)

    fn = sub.add_parser("functions", help="设备功能视图（物模型能力清单）")
    fn.add_argument("device_id")
    fn.add_argument("--category", default="")
    fn.add_argument("--product", default="")
    fn.set_defaults(func=cmd_functions)

    ex = sub.add_parser("exec", help="物模型指令下发")
    ex.add_argument("device_id")
    ex.add_argument("actions_json")
    ex.set_defaults(func=cmd_exec)

    s = sub.add_parser("status", help="查状态")
    s.add_argument("device_ids", nargs="*")
    s.add_argument("--query", default="", help="自然语言问，如 空调现在几度")
    s.set_defaults(func=cmd_status)

    c = sub.add_parser("control", help="白电控制：空调/冰箱/洗衣机/干衣机，传用户原话")
    c.add_argument("query")
    c.add_argument("--device", default="")
    c.add_argument("--category", default="")
    c.set_defaults(func=cmd_control)

    t = sub.add_parser("tv", help="电视控制，传用户原话")
    t.add_argument("query")
    t.add_argument("--device", default="")
    t.set_defaults(func=cmd_tv)

    dg = sub.add_parser("diag", help="一键自检：沙箱代理有没有注入网关凭证")
    dg.set_defaults(func=cmd_diag)
    return p


def main():
    args = build_parser().parse_args()
    print(json.dumps(args.func(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HisenseError as e:
        print(json.dumps({"ok": False, "error": str(e), "code": e.code}, ensure_ascii=False), file=sys.stderr)
        sys.exit(EXIT_RUNTIME)
    except KeyboardInterrupt:
        sys.exit(130)
