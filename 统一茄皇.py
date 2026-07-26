# -*- coding: utf-8 -*-
"""
统一茄皇青龙脚本 v1.0.3

功能：自动登录、活动开卡、签到、浏览/分享任务、好友能量、浇水
环境变量：TYQH (格式: wid1@手机号1&wid2@手机号2，也支持 wid@openId@手机号)

更新说明:
### 2026.07.26
v1.0.3:
- 风控优化：增加随机间隔和频控退避

### 2026.07.23
v1.0.2:
- 日志脱敏：隐藏 wid、手机号和 openId
- 活动优化：自动开活动卡并收取好友能量
- 邀请功能：新用户自动携带配置的邀请码

### 2026.01.31
v1.0.1:
- 性能重构：复用 Session，整理配置和通用函数
- 问题修复：修复浇水变量作用域并完善异常处理
- 格式兼容：支持 @ 与 # 分隔

配置说明:
1. 环境变量设置：
   - TYQH: 用户信息，多账号用 & 分隔
   - 官方接口仅需 wid；手机号和 openId 可选
   - 可选映射：TYQH_OPENID_MAP、TYQH_TOKEN_MAP、TYQH_UA

2. 获取方法：
   - 打开微信小程序 "统一梦时代"
   - 进入个人中心查看客户编号（即 wid）

定时规则建议 (Cron):
0 7,12,18 * * *

From: YaoHuo8648
Email: zheyizzf@188.com
Update: 2026.07.26
"""

import base64
import json
import os
import random
import re
import time
from collections import defaultdict
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
import urllib3
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    from notify import send  # type: ignore
except Exception:
    def send(title, content):
        print(_redact_text(f"[notify-fallback] {title}\n{content}"))


# ==================== 配置常量 ====================
# 邀请开关：1=开启。未参加活动的账号首次登录会绑定下方邀请人；改为 0 可关闭。
TYQH_INVITE_OPT_IN = 1
INVITER_TOMATO_USER_ID = "11422"  # 茄皇活动邀请人的 tomatoUserId

# 风控节奏（秒）：普通动作、功能阶段、账号切换、触发频控后的递增退避。
ACTION_DELAY_RANGE = (2.5, 5.0)
PHASE_DELAY_RANGE = (8.0, 15.0)
ACCOUNT_DELAY_RANGE = (30.0, 60.0)
RATE_LIMIT_DELAY_RANGE = (15.0, 25.0)

BASE_URL = "https://farmgames.ioutu.cn"
PUBLIC_KEY_URL = f"{BASE_URL}/api/web/open/encrypt/public-key"
LOGIN_URL = f"{BASE_URL}/api/web/open/tomato/login"
HOME_URL = f"{BASE_URL}/api/web/member/tomato/home"
TASKS_URL = f"{BASE_URL}/api/web/member/tomato/tasks"
TASK_COMPLETE_URL = f"{BASE_URL}/api/web/member/tomato/tasks/complete"
ENERGY_USE_URL = f"{BASE_URL}/api/web/member/tomato/energy/use"
PAGE_VISIT_URL = f"{BASE_URL}/api/web/member/tomato/page-visit"
CARD_STATUS_URL = f"{BASE_URL}/api/web/member/tomato/cardStatus"
FRIENDS_URL = f"{BASE_URL}/api/web/member/tomato/friends"
FRIEND_STEAL_URL = f"{FRIENDS_URL}/steal"

DEFAULT_PUBLIC_KEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA70sK419vy3MabW3lEGlk7Zh1u78OdnVlioVazp5Y"
    "46eBh+/TDqo/wZ9VrQ/4MmAtoP0vJ2vmwP5gqO3WPojb07WddXfF1eU+5M+Rj3s0eSRrvZvBcGZ3qK0dOgZJ"
    "ScK66IDQazt/c4xqhDcsItIyNRahUqB/IKc6E80GZJvMvFtZVSCseAXC0mAJXhi1AdUOlP+3Pv0fiUVejTJp1"
    "j7LBNWJ7Z5/8mRcclQH0vmxsdYsaV3qZiJ2d/CfNoKcwmI2IWmeZy8NP5U8Hn0AsxPEwjdHoEqG/iy/SoA46T"
    "ZL+RLtWqUSHXpaKR/VFN0rbl25SE91X8FTfLqyD8LfGMCwRQIDAQAB"
)

user_agent = os.getenv(
    "TYQH_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf2541b18) XWEB/20079 miniProgram/wx532ecb3bdaaf92f9",
)

STEP_ORDER = ["登录", "主页", "开卡", "签到", "浏览任务", "分享任务", "浇水", "信息"]
STEP_EMOJI = {
    "登录": "🔑",
    "主页": "🏠",
    "开卡": "💳",
    "签到": "📅",
    "浏览任务": "🔍",
    "分享任务": "📤",
    "浇水": "💧",
    "信息": "ℹ️",
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PUBLIC_KEY_B64 = DEFAULT_PUBLIC_KEY_B64
_PUBLIC_KEY_OBJ = None
_SENSITIVE_VALUES = set()
_PHONE_PATTERN = re.compile(r"(?<!\d)1\d{10}(?!\d)")


def mask_identifier(value: object) -> str:
    """在展示边界保留少量线索，避免账号标识进入日志。"""
    text = str(value or "")
    if not text:
        return "-"
    if re.fullmatch(r"1\d{10}", text):
        return f"{text[:3]}****{text[-4:]}"
    if len(text) <= 4:
        return "*" * len(text)
    if len(text) <= 8:
        return f"{text[:2]}***{text[-2:]}"
    return f"{text[:3]}***{text[-3:]}"


def _register_sensitive(*values: object):
    for value in values:
        text = str(value or "")
        if len(text) >= 3:
            _SENSITIVE_VALUES.add(text)


def _redact_text(value: object) -> str:
    text = str(value)
    for secret in sorted(_SENSITIVE_VALUES, key=len, reverse=True):
        text = text.replace(secret, mask_identifier(secret))
    return _PHONE_PATTERN.sub(lambda match: mask_identifier(match.group(0)), text)


def _parse_kv_map(raw: str) -> Dict[str, str]:
    result = {}
    if not raw:
        return result
    for item in re.split(r"[&,;\n]", raw):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            k, v = item.split(":", 1)
        elif "=" in item:
            k, v = item.split("=", 1)
        else:
            continue
        result[k.strip()] = v.strip()
    return result


def parse_users() -> List[Dict[str, str]]:
    raw_users = [x.strip() for x in os.getenv("TYQH", "").split("&") if x.strip()]
    openid_map = _parse_kv_map(os.getenv("TYQH_OPENID_MAP", ""))
    token_map = _parse_kv_map(os.getenv("TYQH_TOKEN_MAP", ""))
    users = []
    for item in raw_users:
        parts = [p.strip() for p in re.split(r"[@#]", item) if p.strip()]
        if not parts:
            continue
        wid = parts[0]
        open_id = ""
        phone = ""
        if len(parts) == 1:
            open_id = openid_map.get(wid, "")
        elif len(parts) == 2:
            second = parts[1]
            if re.fullmatch(r"1\d{10}", second):
                phone = second
                open_id = openid_map.get(wid, "")
            else:
                open_id = second
        else:
            a, b = parts[1], parts[2]
            if re.fullmatch(r"1\d{10}", a) and not re.fullmatch(r"1\d{10}", b):
                phone, open_id = a, b
            elif re.fullmatch(r"1\d{10}", b) and not re.fullmatch(r"1\d{10}", a):
                open_id, phone = a, b
            else:
                open_id, phone = a, b
        users.append(
            {
                "wid": wid,
                "openId": open_id,
                "phone": phone,
                "token": token_map.get(wid, ""),
            }
        )
    return users


def _short(s: str, n: int = 120) -> str:
    s = str(s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _strip_step_prefix(line: str) -> str:
    s = str(line).strip()
    # 去掉已有的 "🔑 登录: " / "🔑 登录: 🔑 登录: " 这类重复前缀
    for _ in range(3):
        old = s
        for step, emoji in STEP_EMOJI.items():
            s = re.sub(rf"^(?:{re.escape(emoji)}\s*)?{re.escape(step)}\s*[:：]\s*", "", s)
        if s == old:
            break
    return s


def _step_key(line: str) -> str:
    for k in STEP_ORDER:
        emoji = STEP_EMOJI.get(k, "")
        if emoji and line.lstrip().startswith(emoji):
            return k
    for k in STEP_ORDER:
        if k in line:
            return k
    return "信息"


def _pull_resource_snapshot(lines):
    """从日志提取最终资源。避免把“今日已用能量=20”误当成当前能量。"""
    res = {}
    for line in reversed(lines):
        m = re.search(r"能量☀️\s*(\d+)", line)
        if not m:
            m = re.search(r"(?<!已用)能量\s*[=:：]\s*(\d+)", line)
        if m and "energy" not in res:
            res["energy"] = int(m.group(1))

        m = re.search(r"番茄🍅\s*(\d+)", line)
        if not m:
            m = re.search(r"番茄\s*[=:：]\s*(\d+)", line)
        if m and "tomato" not in res:
            res["tomato"] = int(m.group(1))

        m = re.search(r"阶段\s*[=:：]?\s*([^\s|]+)", line)
        if m and "stage" not in res:
            res["stage"] = m.group(1).lstrip("=:：")

        if len(res) >= 3:
            break
    return res


def log_step(user_logs: list, step: str, msg: str):
    emoji = STEP_EMOJI.get(step, "•")
    safe_msg = _redact_text(msg)
    line = f"{emoji} {step}: {safe_msg}"
    print(safe_msg if step == "信息" else f"{step}: {safe_msg}")
    user_logs.append(line)


def render_report(all_lines):
    blocks, cur = [], []
    for ln in all_lines:
        if ln.strip().startswith("👤 用户"):
            if cur:
                blocks.append(cur)
            cur = [ln.strip()]
        elif ln is not None:
            cur.append(ln.rstrip())
    if cur:
        blocks.append(cur)

    out = []
    for b in blocks:
        if not b:
            continue
        out.append("━━━━━━━━━━━━━━━━━━━━━━")
        out.append(b[0].strip())
        bucket = defaultdict(list)
        for ln in b[1:]:
            if not ln.strip():
                continue
            bucket[_step_key(ln)].append(ln)
        snap = _pull_resource_snapshot(b)
        if snap:
            res_line = "📊 当前资源："
            if "energy" in snap:
                res_line += f"☀️{snap['energy']}  "
            if "tomato" in snap:
                res_line += f"🍅{snap['tomato']}  "
            if "stage" in snap:
                res_line += f"阶段={snap['stage']}  "
            out.append(res_line.rstrip())
        for step in STEP_ORDER:
            lines = bucket.get(step) or []
            if not lines:
                continue
            best = _strip_step_prefix(lines[-1])
            out.append(f"{STEP_EMOJI.get(step, '•')} {step}: {_short(best, 100)}")
    out.append("━━━━━━━━━━━━━━━━━━━━━━")
    return _redact_text("\n".join(out))


def sleep_human(a=1.2, b=2.4):
    time.sleep(random.uniform(a, b))


def clean_public_key(key: str) -> str:
    return (
        key.replace("-----BEGIN PUBLIC KEY-----", "")
        .replace("-----END PUBLIC KEY-----", "")
        .replace("\\n", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
    )


def load_public_key(b64_key: str = None):
    global _PUBLIC_KEY_OBJ, _PUBLIC_KEY_B64
    key_b64 = clean_public_key(b64_key or _PUBLIC_KEY_B64)
    der = base64.b64decode(key_b64)
    _PUBLIC_KEY_OBJ = serialization.load_der_public_key(der)
    _PUBLIC_KEY_B64 = key_b64
    return _PUBLIC_KEY_OBJ


def refresh_public_key(session: requests.Session) -> str:
    global _PUBLIC_KEY_B64
    try:
        resp = session.get(PUBLIC_KEY_URL, timeout=15)
        data = resp.json()
        candidates = []
        if isinstance(data, dict):
            d = data.get("data")
            if isinstance(d, dict):
                candidates.extend([d.get("publicKey"), d.get("public_key"), d.get("key")])
            elif isinstance(d, str):
                candidates.append(d)
            candidates.extend([data.get("publicKey"), data.get("public_key")])
        for c in candidates:
            if isinstance(c, str) and "MIIB" in c:
                load_public_key(c)
                return _PUBLIC_KEY_B64
    except Exception as e:
        print(_redact_text(f"刷新公钥失败，使用内置公钥: {e}"))
    load_public_key(DEFAULT_PUBLIC_KEY_B64)
    return _PUBLIC_KEY_B64


def encrypt_request_body(payload: dict, public_key_b64: str = None) -> dict:
    pub = load_public_key(public_key_b64) if public_key_b64 else (_PUBLIC_KEY_OBJ or load_public_key())
    aes_key = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    data_bytes = AESGCM(aes_key).encrypt(iv, plaintext, None)
    encrypted_key = pub.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return {
        "data": base64.b64encode(data_bytes).decode(),
        "key": base64.b64encode(encrypted_key).decode(),
        "iv": base64.b64encode(iv).decode(),
    }


def build_session(wid: str = "", open_id: str = "", token: str = "") -> requests.Session:
    s = requests.Session()
    referer = f"{BASE_URL}/"
    qs = []
    if wid:
        qs.append(f"wid={wid}")
    if open_id:
        qs.append(f"openId={open_id}")
    if qs:
        referer = f"{BASE_URL}/?{'&'.join(qs)}"
    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": referer,
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if token:
        headers["Authorization"] = token
        s.cookies.set("authorization", token, domain="farmgames.ioutu.cn")
    s.headers.update(headers)
    return s


def ok(data: dict) -> bool:
    return bool(data) and (data.get("code") == 200 or data.get("success") is True)


def is_rate_limited(data: dict) -> bool:
    msg = str((data or {}).get("msg") or "")
    return any(
        marker in msg
        for marker in ("频繁", "稍后再试", "稍后重试", "活动火热进行中")
    )


def is_need_open_card(data: dict) -> bool:
    msg = str((data or {}).get("msg") or "")
    return "开卡" in msg


def api_get(session: requests.Session, url: str, timeout=20, params: dict = None) -> dict:
    resp = session.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def api_post_encrypted(session: requests.Session, url: str, payload: dict, timeout=20) -> dict:
    body = encrypt_request_body(payload)
    headers = {
        "Content-Type": "application/json",
        "X-Request-Encrypted": "true",
    }
    resp = session.post(url, data=json.dumps(body, separators=(",", ":")), headers=headers, timeout=timeout)
    try:
        data = resp.json()
    except Exception:
        resp.raise_for_status()
        raise
    if resp.status_code >= 400:
        raise requests.HTTPError(f"{resp.status_code} {data}", response=resp)
    return data


def request_with_retry(func, *args, retries=3, base_sleep=2.0, **kwargs):
    last = None
    for i in range(retries):
        last = func(*args, **kwargs)
        if ok(last):
            return last
        if is_rate_limited(last) and i < retries - 1:
            low = max(base_sleep, RATE_LIMIT_DELAY_RANGE[0])
            high = max(low, RATE_LIMIT_DELAY_RANGE[1])
            wait = random.uniform(low, high) * (i + 1)
            print(f"触发频控，{wait:.1f}s 后重试 ({i+1}/{retries-1}) ...")
            time.sleep(wait)
            continue
        return last
    return last


def login(session: requests.Session, wid: str, open_id: str = "", phone: str = "", user_logs: list = None) -> Optional[dict]:
    step = "登录"
    if user_logs is None:
        user_logs = []
    _register_sensitive(wid, open_id, phone)
    if not wid:
        log_step(user_logs, step, "缺少 wid，无法登录 ❌")
        return None
    try:
        refresh_public_key(session)
        payload = {"wid": str(wid), "queryCardStatus": True}
        if open_id:
            payload["openId"] = open_id
        if phone:
            payload["wm_phone"] = phone
            payload["mobile"] = phone
        if TYQH_INVITE_OPT_IN == 1:
            payload["shareTomatoUserId"] = INVITER_TOMATO_USER_ID

        data = request_with_retry(api_post_encrypted, session, LOGIN_URL, payload, retries=2, base_sleep=1.5)
        if ok(data) and isinstance(data.get("data"), dict) and data["data"].get("token"):
            info = data["data"]
            token = info["token"]
            _register_sensitive(
                token,
                info.get("wid"),
                info.get("openId"),
                info.get("mobile"),
                info.get("tomatoUserId"),
            )
            session.headers["Authorization"] = token
            session.cookies.set("authorization", token, domain="farmgames.ioutu.cn")
            returned_mobile = str(info.get("mobile") or "")
            warn = ""
            if phone and returned_mobile and phone != returned_mobile:
                warn = f" ⚠️配置手机号{phone}与返回{returned_mobile}不一致(以wid对应账号为准)"
            mode = "wid+openId" if open_id else ("wid+手机号" if phone else "仅wid")
            card = info.get("cardStatus")
            msg = (
                f"登录成功[{mode}] ✅ 用户={info.get('nickName','')} "
                f"手机={mask_identifier(returned_mobile or phone)} "
                f"tomatoUserId={mask_identifier(info.get('tomatoUserId'))} "
                f"能量={info.get('energyBalance')} 番茄={info.get('tomatoBalance')} "
                f"阶段={info.get('stageName','')} 开卡={card}{warn}"
            )
            log_step(user_logs, step, msg)
            sleep_human(*ACTION_DELAY_RANGE)
            return info
        log_step(user_logs, step, f"登录失败: {_short(data)} ❌")
        return None
    except Exception as e:
        log_step(user_logs, step, f"登录出错: {e} ❌")
        return None


def fetch_home(session: requests.Session, user_logs: list) -> Optional[dict]:
    step = "主页"
    try:
        data = request_with_retry(api_get, session, HOME_URL, retries=2, base_sleep=1.2)
        if ok(data) and isinstance(data.get("data"), dict):
            info = data["data"]
            msg = (
                f"主页同步成功 ✅ 能量☀️{info.get('energyBalance')} "
                f"番茄🍅{info.get('tomatoBalance')} 阶段={info.get('stageName')} "
                f"经验={info.get('currentExp')}/{info.get('stageRequiredExp')} "
                f"今日已用能量={info.get('todayUsedEnergy')} 开卡={info.get('cardStatus')}"
            )
            log_step(user_logs, step, msg)
            return info
        log_step(user_logs, step, f"主页失败: {_short(data)} ❌")
        return None
    except Exception as e:
        log_step(user_logs, step, f"主页出错: {e} ❌")
        return None


def fetch_card_status(session: requests.Session) -> str:
    """返回 '1' 已开卡 / '0' 未开卡 / '' 未知。"""
    try:
        data = api_get(session, CARD_STATUS_URL)
        if ok(data):
            d = data.get("data") or {}
            if isinstance(d, dict):
                return str(d.get("cardStatus") or d.get("status") or "")
            return str(d)
    except Exception:
        pass
    return ""


def ensure_card_opened(session: requests.Session, login_info: dict, user_logs: list) -> bool:
    step = "开卡"
    status = str((login_info or {}).get("cardStatus") or "")
    if status not in {"0", "1"}:
        status = fetch_card_status(session)
    if status == "1":
        log_step(user_logs, step, "茄皇活动卡已开通 ✅")
        return True
    if status == "0":
        log_step(
            user_logs,
            step,
            "活动登录已请求自动开卡，但返回状态仍为未开通 ⚠️",
        )
        return False
    # 未知时不硬拦，交给接口返回
    log_step(user_logs, step, f"开卡状态未知({status or '空'})，继续尝试 ⚠️")
    return True


def fetch_tasks(session: requests.Session) -> List[dict]:
    data = request_with_retry(api_get, session, TASKS_URL, retries=2, base_sleep=1.2)
    if not ok(data):
        raise RuntimeError(f"获取任务失败: {data}")
    rows = data.get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("list") or rows.get("rows") or []
    return rows if isinstance(rows, list) else []


def complete_task(session: requests.Session, task: dict) -> dict:
    payload = {
        "taskType": task.get("taskType") or "",
        "browseTarget": task.get("browseTarget") or "",
    }
    return request_with_retry(
        api_post_encrypted,
        session,
        TASK_COMPLETE_URL,
        payload,
        retries=4,
        base_sleep=2.5,
    )


def collect_friend_energy(session: requests.Session, user_logs: list) -> dict:
    """按官方好友列表 -> 好友主页 -> 收取接口顺序处理可收能量。"""
    result = {"checked": 0, "collected": 0, "energy": 0, "failed": 0}
    page_num = 1
    page_size = 20
    try:
        while True:
            data = request_with_retry(
                api_get,
                session,
                FRIENDS_URL,
                retries=2,
                base_sleep=1.2,
                params={"pageNum": page_num, "pageSize": page_size},
            )
            if not ok(data):
                raise RuntimeError(f"获取好友列表失败: {data}")

            rows = data.get("rows") or []
            if not isinstance(rows, list):
                rows = []
            try:
                total = int(data.get("total") or 0)
            except (TypeError, ValueError):
                total = 0

            for friend in rows:
                friend_id = str((friend or {}).get("friendTomatoUserId") or "")
                if not friend_id:
                    continue
                _register_sensitive(friend_id)
                result["checked"] += 1
                try:
                    home_data = request_with_retry(
                        api_get,
                        session,
                        f"{FRIENDS_URL}/{friend_id}/home",
                        retries=2,
                        base_sleep=1.0,
                    )
                    if not ok(home_data) or not isinstance(home_data.get("data"), dict):
                        result["failed"] += 1
                        continue
                    home = home_data["data"]
                    try:
                        available = int(home.get("stealAmount") or 0)
                    except (TypeError, ValueError):
                        available = 0
                    if str(home.get("canSteal") or "") != "1" or available <= 0:
                        continue

                    steal_data = request_with_retry(
                        api_post_encrypted,
                        session,
                        FRIEND_STEAL_URL,
                        {"friendTomatoUserId": friend_id},
                        retries=2,
                        base_sleep=1.2,
                    )
                    if ok(steal_data):
                        gained = steal_data.get("data")
                        if isinstance(gained, dict):
                            gained = gained.get("stealAmount") or gained.get("energyAmount")
                        try:
                            gained = int(gained)
                        except (TypeError, ValueError):
                            gained = available
                        result["collected"] += 1
                        result["energy"] += gained
                    else:
                        result["failed"] += 1
                except Exception:
                    result["failed"] += 1
                finally:
                    sleep_human(*ACTION_DELAY_RANGE)

            if not rows or (total and result["checked"] >= total) or len(rows) < page_size:
                break
            page_num += 1

        log_step(
            user_logs,
            "信息",
            f"好友能量：检查{result['checked']}人，收取{result['collected']}人，"
            f"共{result['energy']}能量，失败{result['failed']}人",
        )
    except Exception as e:
        log_step(user_logs, "信息", f"好友能量处理失败: {e} ❌")
    return result


def do_sign_and_browse_tasks(session: requests.Session, user_logs: list, card_opened: bool = True):
    try:
        tasks = fetch_tasks(session)
    except Exception as e:
        log_step(user_logs, "签到", f"获取任务列表失败: {e} ❌")
        log_step(user_logs, "浏览任务", f"获取任务列表失败: {e} ❌")
        return

    if not tasks:
        log_step(user_logs, "签到", "任务列表为空 ⚠️")
        log_step(user_logs, "浏览任务", "任务列表为空 ⚠️")
        return

    # 分类汇总，避免“任务列表 + 逐步复述”重复刷屏
    done_by_step = {"签到": [], "浏览任务": [], "分享任务": []}
    todo = []
    other_tasks = []

    for task in tasks:
        ttype = (task.get("taskType") or "").upper()
        tname = task.get("taskName") or ttype
        completed = str(task.get("completed") or "0")
        action_type = (task.get("actionType") or "").upper()
        is_done = completed == "1" or action_type == "DONE"

        if ttype == "FRIEND_STEAL_ENERGY":
            continue
        if ttype == "SIGN":
            if is_done:
                done_by_step["签到"].append(tname)
            else:
                todo.append(task)
            continue
        if ttype == "BROWSE":
            if is_done:
                done_by_step["浏览任务"].append(tname)
            else:
                todo.append(task)
            continue
        if ttype == "SHARE":
            if is_done:
                done_by_step["分享任务"].append(tname)
            else:
                todo.append(task)
            continue
        other_tasks.append(task)

    # 已完成任务：每类只汇总一句
    if done_by_step["签到"]:
        log_step(user_logs, "签到", f"今日已完成 ✅ ({'、'.join(done_by_step['签到'])})")
    if done_by_step["浏览任务"]:
        log_step(user_logs, "浏览任务", f"已完成 ✅ ({'、'.join(done_by_step['浏览任务'])})")
    if done_by_step["分享任务"]:
        log_step(user_logs, "分享任务", f"已完成 ✅ ({'、'.join(done_by_step['分享任务'])})")

    if not card_opened:
        for task in todo + other_tasks:
            ttype = (task.get("taskType") or "").upper()
            tname = task.get("taskName") or ttype
            if ttype == "SIGN":
                log_step(user_logs, "签到", f"{tname} 跳过：账号未开卡 ⚠️")
            elif ttype == "BROWSE":
                log_step(user_logs, "浏览任务", f"{tname} 跳过：账号未开卡 ⚠️")
            elif ttype == "SHARE":
                log_step(user_logs, "分享任务", f"{tname} 跳过：账号未开卡 ⚠️")
            else:
                log_step(user_logs, "信息", f"{tname} 跳过：账号未开卡 ⚠️")
        return

    # 仅对未完成任务执行并输出
    for task in todo:
        ttype = (task.get("taskType") or "").upper()
        tname = task.get("taskName") or ttype
        step_name = {"SIGN": "签到", "BROWSE": "浏览任务", "SHARE": "分享任务"}.get(ttype)
        if not step_name:
            continue
        try:
            if ttype == "BROWSE" and task.get("browseTarget"):
                try:
                    api_post_encrypted(
                        session,
                        PAGE_VISIT_URL,
                        {"pagePath": str(task.get("browseTarget"))[:500]},
                    )
                except Exception:
                    pass
                sleep_human(*ACTION_DELAY_RANGE)

            result = complete_task(session, task)
            if ok(result):
                data = result.get("data") or {}
                reward = data.get("rewardText") or f"+{data.get('rewardEnergy', task.get('rewardEnergy', ''))} 能量"
                log_step(user_logs, step_name, f"{tname} 完成成功 ✅ 奖励={reward}")
            elif is_need_open_card(result):
                log_step(user_logs, step_name, f"{tname} 失败: 请先开卡后再操作 ⚠️")
            else:
                log_step(user_logs, step_name, f"{tname} 失败: {_short(result)} ❌")
            sleep_human(*ACTION_DELAY_RANGE)
        except Exception as e:
            log_step(user_logs, step_name, f"{tname} 出错: {e} ❌")

    for task in other_tasks:
        ttype = (task.get("taskType") or "").upper()
        tname = task.get("taskName") or ttype
        log_step(user_logs, "信息", f"暂不自动处理任务类型 {ttype}: {tname}")


def use_energy_loop(session: requests.Session, home: dict, user_logs: list, max_times: int = 5, card_opened: bool = True):
    step = "浇水"
    energy = int((home or {}).get("energyBalance") or 0)
    if not card_opened:
        log_step(user_logs, step, "账号未开卡，跳过浇水 ⚠️")
        return home
    if energy <= 0:
        log_step(user_logs, step, "当前能量为 0，跳过 ⚠️")
        return home

    success = 0
    last_info = home
    for _ in range(max_times):
        try:
            data = request_with_retry(
                api_post_encrypted,
                session,
                ENERGY_USE_URL,
                {"syncHomeInfo": True},
                retries=4,
                base_sleep=2.5,
            )
            if not ok(data):
                msg = data.get("msg") or _short(data)
                if success == 0:
                    log_step(user_logs, step, f"浇水失败: {msg} ❌")
                else:
                    log_step(user_logs, step, f"共成功 {success} 次后停止: {msg} ⚠️")
                break
            info = data.get("data") or {}
            last_info = info if isinstance(info, dict) and info else last_info
            success += 1
            energy_now = info.get("energyBalance", "?")
            stage = info.get("stageName", last_info.get("stageName", ""))
            exp = f"{info.get('currentExp', '?')}/{info.get('stageRequiredExp', '?')}"
            print(f"浇水#{success} 成功 能量={energy_now} 经验={exp} 阶段={stage}")
            try:
                if int(info.get("energyBalance", 0)) <= 0:
                    break
            except Exception:
                break
            sleep_human(*ACTION_DELAY_RANGE)
        except Exception as e:
            log_step(user_logs, step, f"浇水异常: {e} ❌")
            break

    if success > 0:
        log_step(
            user_logs,
            step,
            f"浇水成功 {success} 次 ✅ "
            f"能量☀️{last_info.get('energyBalance', '?')} "
            f"番茄🍅{last_info.get('tomatoBalance', '?')} "
            f"经验={last_info.get('currentExp', '?')}/{last_info.get('stageRequiredExp', '?')} "
            f"阶段={last_info.get('stageName', '?')}",
        )
    return last_info


def process_user(user: dict, user_index: int) -> List[str]:
    wid = user.get("wid", "")
    open_id = user.get("openId", "")
    phone = user.get("phone", "")
    preset_token = user.get("token", "")
    _register_sensitive(wid, open_id, phone, preset_token)

    user_logs = [
        f"👤 用户{user_index}: wid={mask_identifier(wid)} | "
        f"openId={mask_identifier(open_id)} | 手机号={mask_identifier(phone)}"
    ]
    print(
        f"\n===== 开始处理用户 {user_index} "
        f"(wid: {mask_identifier(wid)}, openId: {mask_identifier(open_id)}, "
        f"手机号: {mask_identifier(phone)}) ====="
    )

    session = build_session(wid=wid, open_id=open_id, token=preset_token)
    load_public_key(DEFAULT_PUBLIC_KEY_B64)

    login_info = None
    if preset_token:
        session.headers["Authorization"] = preset_token
        log_step(user_logs, "登录", "使用 TYQH_TOKEN_MAP 预设 token ⚠️")
        login_info = {"token": preset_token, "cardStatus": ""}
    else:
        login_info = login(session, wid, open_id=open_id, phone=phone, user_logs=user_logs)

    if not login_info:
        log_step(user_logs, "信息", "获取授权失败，无法执行后续操作 🔒")
        print(f"===== 完成处理用户 {user_index} =====")
        return user_logs

    card_opened = ensure_card_opened(session, login_info, user_logs)
    home = fetch_home(session, user_logs) or {}
    # home 里也可能有 cardStatus
    if str(home.get("cardStatus") or "") == "1":
        card_opened = True
    elif str(home.get("cardStatus") or "") == "0":
        card_opened = False

    sleep_human(*PHASE_DELAY_RANGE)
    do_sign_and_browse_tasks(session, user_logs, card_opened=card_opened)
    sleep_human(*PHASE_DELAY_RANGE)
    if card_opened:
        collect_friend_energy(session, user_logs)
    else:
        log_step(user_logs, "信息", "账号活动卡未开通，跳过好友能量 ⚠️")
    sleep_human(*PHASE_DELAY_RANGE)
    home = fetch_home(session, user_logs) or home
    if home:
        sleep_human(*ACTION_DELAY_RANGE)
        use_energy_loop(session, home, user_logs, card_opened=card_opened)
        sleep_human(*ACTION_DELAY_RANGE)
        fetch_home(session, user_logs)

    print(f"===== 完成处理用户 {user_index} =====")
    return user_logs


def main():
    users = parse_users()
    if not users:
        print("未配置 TYQH 账号。格式：TYQH='wid@手机号&wid@手机号'")
        print("也可：TYQH='wid' 或 TYQH='wid@openId'")
        return

    print(f"共检测到 {len(users)} 个用户，开始依次处理... 👥")
    all_logs = []
    for i, user in enumerate(users, 1):
        logs = process_user(user, i)
        all_logs.extend(logs)
        all_logs.append("")
        if i < len(users):
            # 多账号之间使用独立长间隔，避免同一出口 IP 连续登录。
            sleep_human(*ACCOUNT_DELAY_RANGE)

    report = render_report(all_logs)
    print("\n" + "=" * 50)
    print("最终推送通知内容：")
    print(report)
    print("=" * 50)
    try:
        send("统一茄皇", report)
    except Exception as e:
        print(_redact_text(f"推送失败: {e}"))


if __name__ == "__main__":
    main()
