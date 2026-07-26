#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顺丰速运自动任务 v1.1.1

功能：自动执行顺丰速运日常积分任务 + 会员日活动 + 世界杯活动
支持签到、做任务、领积分、会员日抽奖、红包合成与提取、世界杯礼物与射门游戏等

更新说明:
### 2026.07.15
v1.1.1:
- 端午活动替换为世界杯活动，自动按活动日期启停
- 世界杯助力目标使用配置区自有 ID，随机下注默认关闭
- 日常任务码兼容更多跳转字段，人工任务明确跳过

### 2026.06.08
v1.1.0:
- 新增端午活动，支持浏览领奖、砸粽、金币统计和推送汇总
- 新增 CK 失效识别，失效时推送“CK失效了”

### 2026.05.27
v1.0.9:
- 新增顺丰双端签到，保留旧签到接口
- 优化签到日志展示，移除过期周年活动

### 2026.03.22
v1.0.7:
- ✨ 新增会员日活动（每月26-28号自动执行）
- 🎁 会员日支持抽奖、做任务、领奖励、红包合成与提取
- 🎛️ 会员日做成子开关 ENABLE_MEMBER_DAY 控制

配置说明:
1. 账号变量 (sfsyUrl):
    格式: CK值或登录URL[#代理地址]
    示例: sessionId=xxx;_login_mobile_=xxx;_login_user_id_=xxx#http://127.0.0.1:1080
    多账号用 & 分隔

2. 如何抓取 sfsyUrl:
    - 前置条件: 需要先用手机号登录顺丰小程序以及APP
    方法A: 这个网站用微信扫码登录即可获取
      https://sm.linzixuan.top/
    方法B: 手动抓包
      ① 微信打开「顺丰速运」小程序
      ② 使用抓包工具（如 HttpCanary）抓取请求
      ③ 找到 Cookie 中的 sessionId / _login_mobile_ / _login_user_id_ 字段
      ④ 拼接为 sessionId=xxx;_login_mobile_=xxx;_login_user_id_=xxx
      ⑤ 将拼接后的值设为环境变量 sfsyUrl
    注意: CK 过期后需重新抓取

3. 代理设置 (可选，不用代理就不用管):
    - 固定代理：填在 sfsyUrl 账号变量中 CK 最后，用 # 分隔
    - 动态代理：添加环境变量 SF_PROXY_API_URL = 你的代理提取链接
    - 代理类型：添加环境变量 SF_PROXY_TYPE = http 或 socks5 (默认 socks5)

4. 任务开关与并发:
    在下方「配置区域」修改
    ENABLE_DAILY_TASK    = True/False  日常积分任务
    ENABLE_MEMBER_DAY    = True/False  会员日活动 (每月26-28号)
    ENABLE_WORLD_CUP     = True/False  世界杯活动 (2026.07.02-07.20)
    ENABLE_WORLD_CUP_BET = True/False  世界杯随机下注
    CONCURRENT_NUM       = 1~20       并发数量

5. 推送通知 (可选):
    环境变量 SFSY_PUSH = 1 开启推送 (默认), 0 关闭
    依赖青龙自带的 notify.py 模块

定时规则建议 (Cron):
11 6,18 * * *

From: YaoHuo8648
Email: zheyizzf@188.com
Update: 2026.07.15
"""

import hashlib
import json
import os
import random
import re
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import unquote, urlparse, parse_qs, quote as url_encode
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

PUSH_SWITCH = os.getenv("SFSY_PUSH", "1")
try:
    from notify import send as notify_send
    print("✅ 成功加载青龙notify推送模块")
except ImportError:
    print("⚠️ 未找到notify模块，推送功能不可用（本地运行可忽略）")
    notify_send = None

# ==================== 配置区域 ====================
# 功能开关 (True=开启, False=关闭)
ENABLE_DAILY_TASK = True         # 日常积分任务 (签到+做任务+领积分)
ENABLE_MEMBER_DAY = True         # 会员日活动 (每月26-28号自动执行)
ENABLE_WORLD_CUP = True          # 世界杯活动 (2026.07.02-07.20)
ENABLE_WORLD_CUP_BET = False     # 世界杯随机下注，开启会消耗金币
WORLD_CUP_BET_COIN = 10          # 单场下注金币，服务端最低 10
WORLD_CUP_ASSIST_ID = 'F6C60FAD2AD34B6BACF73CA89C064FC3'  # 主账号助力目标
CONCURRENT_NUM = 1               # 并发数量 (1~20)

TOKEN = 'wwesldfs29aniversaryvdld29'
inviteId = []
SYS_CODE = 'MCS-MIMP-CORE'

# 日常任务跳过列表
DAILY_SKIP_TASKS = [
    '用行业模板寄件下单', '用积分兑任意礼品', '参与积分活动',
    '每月累计寄件', '完成每月任务', '去使用AI寄件',
    # 以下任务需要真实寄件或在小程序中设置资料，脚本不冒充完成
    '寄一单国际件', '去新增一个收件偏好', '设置你的顺丰ID',
    '去使用AI小丰寄件',
]

# 会员日跳过任务类型
MEMBER_DAY_SKIP_TASK_TYPES = [
    'SEND_SUCCESS', 'INVITEFRIENDS_PARTAKE_ACTIVITY', 'OPEN_SVIP',
    'OPEN_NEW_EXPRESS_CARD', 'OPEN_FAMILY_CARD', 'CHARGE_NEW_EXPRESS_CARD',
    'INTEGRAL_EXCHANGE',
]

WORLD_CUP_ACTIVITY_CODE = 'WORLD_CUP'
WORLD_CUP_CHANNEL = '26sjbapp'
WORLD_CUP_PLATFORM = 'SFAPP'
WORLD_CUP_CITY_CODE = os.getenv('SF_WORLD_CUP_CITY_CODE', '021')
WORLD_CUP_START = datetime(2026, 7, 2).date()
WORLD_CUP_END = datetime(2026, 7, 20).date()
WORLD_CUP_ENABLE_GAME = True
WORLD_CUP_ENABLE_SETTLE = True
# 不保留来源不明的固定 taskCode，只使用当前任务列表实时返回的 code
WORLD_CUP_SAFE_TASK_NAMES = {
    '浏览积分商城',
    '去看看互寄8折权益',
}
CK_INVALID_KEYWORDS = (
    '未登录', '请登录', '请先登录', '登录失效', '登录已失效',
    '登录过期', '会话失效', 'session失效', 'sessionid失效',
    'sessionid已失效', 'token失效', '重新登录', 'not_login',
    'unauthorized', '用户信息失效',
)

# 代理配置
PROXY_API_URL = os.getenv("SF_PROXY_API_URL", "")
PROXY_TYPE = os.getenv("SF_PROXY_TYPE", "socks5")
PROXY_TIMEOUT = 15
MAX_PROXY_RETRIES = 5
REQUEST_RETRY_COUNT = 3
PROXY_RETRY_DELAY = 2
PROXY_CONTEXT = {'last_fetch_ts': 0}
PROXY_LOCK = threading.Lock()
print_lock = Lock()
# =================================================


def world_cup_active(current_date=None) -> bool:
    current_date = current_date or datetime.now().date()
    return WORLD_CUP_START <= current_date <= WORLD_CUP_END


def is_safe_world_cup_task(task: Dict) -> bool:
    task_name = str(task.get('taskName') or '')
    task_code = str(task.get('taskCode') or '')
    return bool(task_code and task_name in WORLD_CUP_SAFE_TASK_NAMES)


class Logger:
    def __init__(self):
        self.messages: List[str] = []
        self.lock = Lock()

    def _log(self, icon: str, msg: str):
        line = f"{icon} {msg}"
        with print_lock:
            print(line)
        with self.lock:
            self.messages.append(line)

    def info(self, msg): self._log('📝', msg)
    def success(self, msg): self._log('✅', msg)
    def warning(self, msg): self._log('⚠️', msg)
    def error(self, msg): self._log('❌', msg)
    def task(self, msg): self._log('🎯', msg)
    def medal(self, msg): self._log('🏅', msg)
    def points(self, pts, prefix="当前积分"): self._log('💰', f"{prefix}: 【{pts}】")


# ==================== 代理管理器 ====================
def _log_global(msg: str):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] {msg}", flush=True)


def _build_proxy_url(ip: str, port: int, username: str = "", password: str = "") -> str:
    """构建标准代理URL，认证信息自动URL编码"""
    if username and password:
        safe_user = url_encode(username, safe='')
        safe_pass = url_encode(password, safe='')
        return f"{PROXY_TYPE}://{safe_user}:{safe_pass}@{ip}:{port}"
    return f"{PROXY_TYPE}://{ip}:{port}"


def parse_proxy_response(text: str) -> Optional[Tuple[str, str]]:
    """解析代理API响应，返回(代理URL, 显示用字符串)，支持JSON和纯文本格式"""
    text = text.strip()
    try:
        data = json.loads(text)
        def extract(d: dict) -> Optional[Tuple[str, str]]:
            if 'ip' not in d or 'port' not in d:
                return None
            ip, port = str(d['ip']), int(d['port'])
            user = str(d.get('account', d.get('user', '')) or '')
            pwd = str(d.get('password', d.get('pass', '')) or '')
            url = _build_proxy_url(ip, port, user, pwd)
            display = f"{ip}:{port}" + (" (认证)" if user else "")
            return url, display
        if isinstance(data, dict):
            if 'ip' in data and 'port' in data:
                return extract(data)
            if 'data' in data:
                pd = data['data']
                if isinstance(pd, dict) and 'list' in pd:
                    pl = pd['list']
                    if isinstance(pl, list) and pl:
                        return extract(pl[0])
                if isinstance(pd, list) and pd:
                    return extract(pd[0])
                if isinstance(pd, dict) and 'ip' in pd:
                    return extract(pd)
            if 'result' in data:
                r = data['result']
                if isinstance(r, dict) and 'ip' in r:
                    return extract(r)
    except (json.JSONDecodeError, ValueError):
        pass
    if ':' in text:
        segments = text.split()
        addr_parts = segments[0].split(':')
        if len(addr_parts) == 2 and addr_parts[1].isdigit():
            ip, port = addr_parts[0], int(addr_parts[1])
            user = segments[1] if len(segments) > 1 else ""
            pwd = segments[2] if len(segments) > 2 else ""
            url = _build_proxy_url(ip, port, user, pwd)
            display = f"{ip}:{port}" + (" (认证)" if user else "")
            return url, display
    return None


def get_api_proxy() -> Optional[Tuple[Dict[str, str], str]]:
    """从API获取代理，返回(代理字典, 显示用字符串)"""
    if not PROXY_API_URL:
        return None
    with PROXY_LOCK:
        elapsed = time.time() - PROXY_CONTEXT['last_fetch_ts']
        if elapsed < 3:
            time.sleep(3 - elapsed)
        for i in range(MAX_PROXY_RETRIES):
            try:
                resp = requests.get(PROXY_API_URL, timeout=10)
                if resp.status_code == 200:
                    result = parse_proxy_response(resp.text)
                    if result:
                        proxy_url, display = result
                        PROXY_CONTEXT['last_fetch_ts'] = time.time()
                        _log_global(f"✅ 代理获取成功: {display}")
                        return {'http': proxy_url, 'https': proxy_url}, display
                _log_global(f"⚠️ 第{i+1}次代理格式无效")
            except Exception as e:
                _log_global(f"⚠️ 第{i+1}次获取代理异常: {str(e)[:80]}")
            if i < MAX_PROXY_RETRIES - 1:
                time.sleep(PROXY_RETRY_DELAY)
        PROXY_CONTEXT['last_fetch_ts'] = time.time()
        _log_global(f"❌ 代理获取失败：已重试{MAX_PROXY_RETRIES}次")
        return None


def parse_fixed_proxy(fixed_proxy: str) -> Optional[Dict[str, str]]:
    """解析固定代理字符串为代理字典"""
    if not fixed_proxy:
        return None
    if '://' not in fixed_proxy:
        fixed_proxy = f'{PROXY_TYPE}://{fixed_proxy}'
    return {'http': fixed_proxy, 'https': fixed_proxy}


# ==================== HTTP客户端 ====================
class SFHttpClient:
    def __init__(self, fixed_proxy: str = ""):
        self.session = requests.Session()
        self.session.verify = False
        self.proxy_display = '无代理'
        self.ck_invalid = False
        self.ck_invalid_message = ''
        self._setup_proxy(fixed_proxy)
        self.headers = {
            'Host': 'mcs-mimp-web.sf-express.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254173b) XWEB/19027',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'channel': 'xcxpart',
            'platform': 'MINI_PROGRAM',
            'accept-language': 'zh-CN,zh;q=0.9',
        }

    def _setup_proxy(self, fixed_proxy: str):
        if fixed_proxy:
            proxy_dict = parse_fixed_proxy(fixed_proxy)
            if proxy_dict:
                self.session.proxies = proxy_dict
                display = fixed_proxy
                if '@' in fixed_proxy:
                    parts = fixed_proxy.split('@')
                    display = f"***@{parts[-1]}"
                self.proxy_display = display
                return
        result = get_api_proxy()
        if result:
            self.session.proxies = result[0]
            self.proxy_display = result[1]

    def _generate_sign(self) -> Dict[str, str]:
        timestamp = str(int(round(time.time() * 1000)))
        data = f'token={TOKEN}&timestamp={timestamp}&sysCode={SYS_CODE}'
        signature = hashlib.md5(data.encode()).hexdigest()
        return {'syscode': SYS_CODE, 'timestamp': timestamp, 'signature': signature}

    def _check_ck_invalid(self, result: Dict):
        if not isinstance(result, dict) or result.get('success') is True:
            return
        text = ' '.join(str(result.get(k, '')) for k in ('errorMessage', 'message', 'msg', 'error', 'code', 'errorCode')).lower()
        if any(keyword in text for keyword in CK_INVALID_KEYWORDS):
            self.ck_invalid = True
            self.ck_invalid_message = result.get('errorMessage') or result.get('message') or result.get('msg') or 'CK失效了'

    def request(self, url: str, data: Optional[Dict] = None, extra_headers: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        proxy_retry_count = 0
        retry_count = 0
        while proxy_retry_count < MAX_PROXY_RETRIES:
            sign_data = self._generate_sign()
            headers = {**self.headers, **sign_data}
            if extra_headers:
                headers.update(extra_headers)
            try:
                resp = self.session.post(url, headers=headers, json=data or {}, timeout=PROXY_TIMEOUT)
                resp.raise_for_status()
                try:
                    result = resp.json()
                    if result is not None:
                        self._check_ck_invalid(result)
                        return result
                except (json.JSONDecodeError, ValueError):
                    pass
                retry_count += 1
                if retry_count < REQUEST_RETRY_COUNT:
                    time.sleep(2)
                    continue
                return None
            except requests.exceptions.RequestException as e:
                retry_count += 1
                error_str = str(e)
                if 'ProxyError' in error_str or 'SSLError' in error_str or 'ConnectionError' in error_str:
                    proxy_retry_count += 1
                    if proxy_retry_count < MAX_PROXY_RETRIES:
                        result = get_api_proxy()
                        if result:
                            self.session.proxies = result[0]
                            self.proxy_display = result[1]
                        retry_count = 0
                    time.sleep(2)
                    continue
                if retry_count < REQUEST_RETRY_COUNT:
                    time.sleep(2)
                    continue
                return None
            except Exception:
                return None
        return None

    def request_app(self, url: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """APP平台请求"""
        original = self.headers.get('platform', 'MINI_PROGRAM')
        self.headers['platform'] = 'SFAPP'
        try:
            return self.request(url, data)
        finally:
            self.headers['platform'] = original

    def login(self, url: str) -> Tuple[bool, str, str]:
        try:
            decoded = unquote(url)
            if decoded.startswith('sessionId=') or '_login_mobile_=' in decoded:
                cookie_dict = {}
                for item in decoded.split(';'):
                    item = item.strip()
                    if '=' in item:
                        k, v = item.split('=', 1)
                        cookie_dict[k] = v
                for k, v in cookie_dict.items():
                    self.session.cookies.set(k, v, domain='mcs-mimp-web.sf-express.com')
                user_id = cookie_dict.get('_login_user_id_', '')
                phone = cookie_dict.get('_login_mobile_', '')
                return (True, user_id, phone) if phone else (False, '', '')
            else:
                self.session.get(decoded, headers=self.headers, timeout=PROXY_TIMEOUT)
                cookies = self.session.cookies.get_dict()
                user_id = cookies.get('_login_user_id_', '')
                phone = cookies.get('_login_mobile_', '')
                return (True, user_id, phone) if phone else (False, '', '')
        except Exception:
            return False, '', ''


# ==================== 日常积分任务执行器 ====================
class DailyTaskExecutor:
    def __init__(self, http: SFHttpClient, logger: Logger, user_id: str):
        self.http = http
        self.logger = logger
        self.user_id = user_id
        self.total_points = 0
        self.taskId = ""
        self.taskCode = ""
        self.strategyId = 0
        self.title = ""
        self.point = 0

    @staticmethod
    def generate_device_id() -> str:
        result = ''
        for char in 'xxxxxxxx-xxxx-xxxx':
            result += random.choice('abcdef0123456789') if char == 'x' else char
        return result

    def _extract_task_id_from_url(self, url: str) -> str:
        if not url:
            return ''
        try:
            parsed = urlparse(str(url))
            params = parse_qs(parsed.query)
            if '_ug_view_param' in params:
                ug_params = json.loads(unquote(params['_ug_view_param'][0]))
                for key in ('taskId', 'taskCode', 'task_id'):
                    if ug_params.get(key):
                        return str(ug_params[key])
        except Exception:
            pass
        match = re.search(
            r"[\"'](?:taskId|taskCode|task_id)[\"']\s*:\s*[\"']([^\"']+)[\"']",
            unquote(str(url)),
        )
        if match:
            return match.group(1)
        return ''

    def _resolve_task_code(self, task: Dict) -> str:
        code = str(task.get('taskCode') or '').strip()
        if code:
            return code
        for key in ('buttonRedirect', 'taskJumpAddress', 'redirectUrl'):
            extracted = self._extract_task_id_from_url(task.get(key, ''))
            if extracted:
                return extracted
        return ''

    def _set_task_attrs(self, task: Dict):
        self.taskId = str(task.get('taskId') or '')
        self.taskCode = self._resolve_task_code(task)
        try:
            self.strategyId = int(task.get('strategyId') or 0)
        except (TypeError, ValueError):
            self.strategyId = 0
        self.title = str(task.get('title') or '未知任务')
        try:
            self.point = int(task.get('point') or task.get('awardIntegral') or 0)
        except (TypeError, ValueError):
            self.point = 0

    def app_sign_in(self) -> Tuple[bool, str]:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~getUnFetchPointAndDiscount'
        resp = self.http.request_app(url, {})
        if resp and resp.get('success'):
            obj = resp.get('obj', [])
            if obj and isinstance(obj, list) and len(obj) > 0:
                names = [item.get('packetName', '未知') for item in obj]
                self.logger.success(f'[APP签到] 获得【{", ".join(names)}】')
            else:
                self.logger.info('[APP签到] 今日已签到')
            return True, ''
        error_msg = resp.get('errorMessage', '未知错误') if resp else '请求失败'
        if '没有待领取礼包' in error_msg:
            time.sleep(1)
            resp2 = self.http.request_app(url, {})
            if resp2 and resp2.get('success'):
                obj2 = resp2.get('obj', [])
                if obj2 and isinstance(obj2, list) and len(obj2) > 0:
                    names = [item.get('packetName', '未知') for item in obj2]
                    self.logger.success(f'[APP签到] 二次领取【{", ".join(names)}】')
                else:
                    self.logger.info('[APP签到] 今日已签到，无待领取奖励')
                return True, ''
            self.logger.info('[APP签到] 今日已签到')
            return True, ''
        self.logger.error(f'[APP签到] 失败: {error_msg}')
        return False, error_msg

    def sign_in(self) -> Tuple[bool, str]:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralTaskSignPlusService~automaticSignFetchPackage'
        resp = self.http.request(url, {"comeFrom": "vioin", "channelFrom": "WEIXIN"})
        if resp and resp.get('success'):
            obj = resp.get('obj', {})
            count_day = obj.get('countDay', 0)
            packets = obj.get('integralTaskSignPackageVOList', [])
            if packets:
                self.logger.success(f'签到成功，获得【{packets[0].get("packetName", "未知")}】，累计签到【{count_day + 1}】天')
            else:
                self.logger.info(f'今日已签到，累计签到【{count_day + 1}】天')
            return True, ''
        error_msg = resp.get('errorMessage', '未知错误') if resp else '请求失败'
        self.logger.error(f'签到失败: {error_msg}')
        return False, error_msg

    def _format_sign_v2_award(self, obj: Any) -> str:
        if not isinstance(obj, dict):
            return ''
        products = obj.get('award', {}).get('productDTOList', [])
        if isinstance(products, list) and products:
            names = []
            for item in products:
                if not isinstance(item, dict):
                    continue
                name = item.get('productName') or item.get('couponName')
                if name:
                    amount = item.get('amount', 1)
                    names.append(f'{name}x{amount}')
            if names:
                return '、'.join(names)
        award = obj.get('award')
        if isinstance(award, dict):
            return award.get('giftBagName') or award.get('giftBagDesc') or ''
        return obj.get('packetName') or obj.get('giftBagName') or ''

    def _sign_v2(self, platform_type: str) -> bool:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralSignV2Service~sign'
        if platform_type == 'SFAPP':
            name = 'APP'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; M2011K2C Build/SKQ1.211006.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.132 Mobile Safari/537.36 mediaCode=SFEXPRESSAPP-Android-ML',
                'channel': 'doudiappwd',
                'platform': 'SFAPP',
                'deviceid': self.generate_device_id(),
            }
        else:
            name = '小程序'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; M2011K2C Build/SKQ1.211006.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/146.0.7680.177 Mobile Safari/537.36 XWEB/1460075 MMWEBSDK/20250804 MMWEBID/4850 MicroMessenger/8.0.63.2920(0x28003FA6) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 miniProgram/wxd4185d00bf7e08ac',
                'channel': 'wxwddoudi',
                'platform': 'MINI_PROGRAM',
            }
        resp = self.http.request(url, {}, headers)
        if resp and resp.get('success'):
            award_text = self._format_sign_v2_award(resp.get('obj'))
            if award_text:
                self.logger.success(f'[{name}签到] 成功，获得【{award_text}】')
            else:
                self.logger.success(f'[{name}签到] 成功')
            return True
        error_msg = resp.get('errorMessage', '未知错误') if resp else '请求失败'
        if '今日已签到' in error_msg:
            self.logger.info(f'[{name}签到] 今日已签到')
            return True
        self.logger.error(f'[{name}签到] 失败: {error_msg}')
        return False

    def dual_sign_in(self) -> bool:
        app_ok = self._sign_v2('SFAPP')
        time.sleep(1)
        mini_ok = self._sign_v2('MINI_PROGRAM')
        return app_ok or mini_ok

    def get_task_list(self) -> List[Dict]:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~queryPointTaskAndSignFromES'
        all_tasks = []
        seen = set()
        for ct in ['1', '2', '3', '4', '01', '02', '03', '04']:
            data = {'channelType': ct, 'deviceId': self.generate_device_id()}
            resp = self.http.request(url, data)
            if resp and resp.get('success') and resp.get('obj'):
                obj = resp['obj'] or {}
                if ct in ('1', '01') or not self.total_points:
                    self.total_points = int(obj.get('totalPoint', self.total_points) or self.total_points or 0)
                task_items = obj.get('taskTitleLevels') or obj.get('ESobj') or []
                if not isinstance(task_items, list):
                    continue
                for task in task_items:
                    if not isinstance(task, dict):
                        continue
                    task = dict(task)
                    tc = self._resolve_task_code(task)
                    if tc:
                        task['taskCode'] = tc
                    key = tc or f"{task.get('taskId', '')}|{task.get('title', '')}"
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    all_tasks.append(task)
        return all_tasks

    def execute_task(self) -> bool:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonRoutePost/memberEs/taskRecord/finishTask'
        resp = self.http.request(url, {'taskCode': self.taskCode})
        return bool(resp and resp.get('success'))

    def receive_task_reward(self) -> bool:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~fetchIntegral'
        data = {
            "strategyId": self.strategyId, "taskId": self.taskId,
            "taskCode": self.taskCode, "deviceId": self.generate_device_id()
        }
        resp = self.http.request(url, data)
        if resp and resp.get('success'):
            self.logger.success(f'领取奖励: {self.title}')
            return True
        return False

    def get_welfare_list(self) -> List[Dict]:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberGoods~mallGoodsLifeService~list'
        data = {"memGrade": 3, "categoryCode": "SHTQ", "showCode": "SHTQWNTJ"}
        resp = self.http.request(url, data)
        if resp and resp.get('success'):
            result = []
            for module in resp.get('obj', []):
                for goods in module.get('goodsList', []):
                    if goods.get('exchangeStatus') == 1:
                        result.append({
                            'goodsNo': goods.get('goodsNo'),
                            'goodsName': goods.get('goodsName'),
                            'showName': goods.get('showName', ''),
                        })
            return result
        return []

    def receive_welfare(self, goods_no: str, goods_name: str) -> bool:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberGoods~pointMallService~createOrder'
        data = {
            "from": "Point_Mall", "orderSource": "POINT_MALL_EXCHANGE",
            "goodsNo": goods_no, "quantity": 1, "taskCode": self.taskCode
        }
        resp = self.http.request(url, data)
        if resp and resp.get('success'):
            self.logger.success(f'领取特权: {goods_name}')
            return True
        return False

    def handle_welfare_task(self) -> bool:
        welfare_list = self.get_welfare_list()
        if not welfare_list:
            return False
        for w in welfare_list:
            name = f"{w['showName']} - {w['goodsName']}" if w['showName'] else w['goodsName']
            if self.receive_welfare(w['goodsNo'], name):
                return True
            time.sleep(1)
        return False

    def run(self) -> Tuple[int, int]:
        self.logger.info('正在获取日常任务列表...')
        tasks = self.get_task_list()
        if not tasks:
            self.logger.error('获取任务列表失败')
            return 0, 0
        points_before = self.total_points
        self.logger.points(points_before, "执行前积分")
        for task in tasks:
            title = task.get('title', '未知')
            status = task.get('status')
            try:
                status = int(status)
            except (TypeError, ValueError):
                pass
            if status == 3:
                continue
            if title in DAILY_SKIP_TASKS:
                self._set_task_attrs(task)
                if status == 2 and self.taskCode and self.receive_task_reward():
                    continue
                self.logger.info(f'人工任务需在小程序完成，未调用自动完成接口: {title}')
                continue
            self._set_task_attrs(task)
            if not self.taskCode:
                self.logger.info(f'未找到任务码，跳过: {title}')
                continue
            self.logger.task(f'发现任务: {title} (状态: {status})')
            if '领任意生活特权福利' in title:
                if self.handle_welfare_task():
                    time.sleep(2)
                    if self.execute_task():
                        time.sleep(2)
                        self.receive_task_reward()
                time.sleep(3)
                continue
            if status == 1:
                if '连签7天' in title and 'process' in task:
                    cur, tot = map(int, task['process'].split('/'))
                    if cur < tot:
                        self.logger.info(f'【{title}】进度: {task["process"]}')
                        continue
                if self.execute_task():
                    self.logger.success(f'[{title}] 提交成功')
                    time.sleep(2)
                    status = 2
                else:
                    continue
            if status == 2:
                if self.receive_task_reward():
                    continue
                if self.execute_task():
                    time.sleep(2)
                    self.receive_task_reward()
            time.sleep(3)
        tasks = self.get_task_list()
        points_after = self.total_points if tasks else points_before
        self.logger.points(points_after, "执行后积分")
        return points_before, points_after


# ==================== 会员日活动执行器 ====================
class MemberDayExecutor:
    MAX_LEVEL = 8

    def __init__(self, http: SFHttpClient, logger: Logger, user_id: str):
        self.http = http
        self.logger = logger
        self.user_id = user_id
        self.black = False
        self.red_packet_map: Dict[int, int] = {}
        self.packet_threshold = 1 << (self.MAX_LEVEL - 1)

    def _check_black(self, error_message: str) -> bool:
        if '没有资格参与活动' in error_message:
            self.black = True
            self.logger.info('会员日任务风控')
            return True
        return False

    def get_index(self) -> Optional[Dict]:
        available = [inv for inv in inviteId if inv != self.user_id]
        invite_user_id = random.choice(available) if available else ''
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayIndexService~index'
        resp = self.http.request(url, {'inviteUserId': invite_user_id})
        if resp and resp.get('success'):
            return resp.get('obj', {})
        error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
        self.logger.info(f'查询会员日失败: {error_msg}')
        self._check_black(error_msg)
        return None

    def receive_invite_award(self, invite_user_id: str):
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayIndexService~receiveInviteAward'
        resp = self.http.request(url, {'inviteUserId': invite_user_id})
        if resp and resp.get('success'):
            product_name = resp.get('obj', {}).get('productName', '空气')
            self.logger.success(f'会员日邀请奖励: {product_name}')
        else:
            error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
            self.logger.info(f'领取会员日邀请奖励失败: {error_msg}')
            self._check_black(error_msg)

    def lottery(self) -> Optional[str]:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayLotteryService~lottery'
        resp = self.http.request(url, {})
        if resp and resp.get('success'):
            product_name = resp.get('obj', {}).get('productName', '空气')
            self.logger.success(f'会员日抽奖: {product_name}')
            return product_name
        error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
        self.logger.info(f'会员日抽奖失败: {error_msg}')
        self._check_black(error_msg)
        return None

    def get_task_list(self) -> Optional[List[Dict]]:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~activityTaskService~taskList'
        resp = self.http.request(url, {'activityCode': 'MEMBER_DAY', 'channelType': 'MINI_PROGRAM'})
        if resp and resp.get('success'):
            return resp.get('obj', [])
        error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
        self.logger.info(f'查询会员日任务失败: {error_msg}')
        self._check_black(error_msg)
        return None

    def finish_task(self, task: Dict) -> bool:
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberEs~taskRecord~finishTask'
        resp = self.http.request(url, {'taskCode': task['taskCode']})
        if resp and resp.get('success'):
            self.logger.success(f'完成会员日任务[{task["taskName"]}]')
            self.fetch_mix_task_reward(task)
            return True
        error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
        self.logger.info(f'完成会员日任务[{task["taskName"]}]失败: {error_msg}')
        self._check_black(error_msg)
        return False

    def fetch_mix_task_reward(self, task: Dict):
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~activityTaskService~fetchMixTaskReward'
        data = {'taskType': task['taskType'], 'activityCode': 'MEMBER_DAY', 'channelType': 'MINI_PROGRAM'}
        resp = self.http.request(url, data)
        if resp and resp.get('success'):
            self.logger.success(f'领取会员日任务[{task["taskName"]}]奖励')
        else:
            error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
            self.logger.info(f'领取会员日任务[{task["taskName"]}]奖励失败: {error_msg}')
            self._check_black(error_msg)

    def do_tasks(self):
        tasks = self.get_task_list()
        if not tasks:
            return
        for task in tasks:
            if self.black:
                return
            if task['status'] == 1:
                self.fetch_mix_task_reward(task)
        for task in tasks:
            if self.black:
                return
            if task['status'] == 2:
                if task['taskType'] in MEMBER_DAY_SKIP_TASK_TYPES:
                    continue
                for _ in range(task.get('restFinishTime', 0)):
                    if self.black:
                        return
                    self.finish_task(task)

    def red_packet_status(self):
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayPacketService~redPacketStatus'
        resp = self.http.request(url, {})
        if not (resp and resp.get('success')):
            error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
            self.logger.info(f'查询会员日合成失败: {error_msg}')
            self._check_black(error_msg)
            return
        for packet in resp.get('obj', {}).get('packetList', []):
            self.red_packet_map[packet['level']] = packet['count']
        for level in range(1, self.MAX_LEVEL):
            count = self.red_packet_map.get(level, 0)
            while count >= 2:
                self.red_packet_merge(level)
                count -= 2
        summary = [f"[{lv}级]X{ct}" for lv, ct in self.red_packet_map.items() if ct > 0]
        self.logger.info(f'会员日合成列表: {", ".join(summary)}')
        if self.red_packet_map.get(self.MAX_LEVEL):
            self.logger.success(f'会员日已拥有[{self.MAX_LEVEL}级]红包X{self.red_packet_map[self.MAX_LEVEL]}')
            self.red_packet_draw(self.MAX_LEVEL)
        else:
            remaining_needed = sum(
                1 << (int(lv) - 1) for lv, ct in self.red_packet_map.items()
                if ct > 0 and int(lv) < self.MAX_LEVEL
            )
            remaining = self.packet_threshold - remaining_needed
            self.logger.info(f'会员日距离[{self.MAX_LEVEL}级]红包还差: [1级]红包X{remaining}')

    def red_packet_merge(self, level: int):
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayPacketService~redPacketMerge'
        resp = self.http.request(url, {'level': level, 'num': 2})
        if resp and resp.get('success'):
            self.logger.success(f'会员日合成: [{level}级]红包X2 -> [{level + 1}级]红包')
            self.red_packet_map[level] -= 2
            self.red_packet_map[level + 1] = self.red_packet_map.get(level + 1, 0) + 1
        else:
            error_msg = resp.get('errorMessage', '无返回') if resp else '请求失败'
            self.logger.info(f'会员日合成[{level}级]红包失败: {error_msg}')
            self._check_black(error_msg)

    def red_packet_draw(self, level: int):
        url = 'https://mcs-mimp-web.sf-express.com/mcs-mimp/commonPost/~memberNonactivity~memberDayPacketService~redPacketDraw'
        resp = self.http.request(url, {'level': str(level)})
        if resp and resp.get('success'):
            coupon_names = [item['couponName'] for item in resp.get('obj', [])] or []
            self.logger.success(f'会员日提取[{level}级]红包: {", ".join(coupon_names) or "空气"}')
        else:
            error_msg = resp.get('errorMessage', '') if resp else '无返回'
            self.logger.info(f'会员日提取[{level}级]红包失败: {error_msg}')
            self._check_black(error_msg)

    def run(self) -> Dict[str, Any]:
        result = {'lottery_prizes': [], 'tasks_done': 0}
        index_info = self.get_index()
        if not index_info or self.black:
            return result
        available = [inv for inv in inviteId if inv != self.user_id]
        invite_user_id = random.choice(available) if available else ''
        if index_info.get('canReceiveInviteAward') and invite_user_id:
            self.receive_invite_award(invite_user_id)
        self.red_packet_status()
        lottery_num = index_info.get('lotteryNum', 0)
        self.logger.info(f'会员日可抽奖 {lottery_num} 次')
        for _ in range(lottery_num):
            if self.black:
                break
            prize = self.lottery()
            if prize:
                result['lottery_prizes'].append(prize)
        if not self.black:
            self.do_tasks()
        if not self.black:
            self.red_packet_status()
        return result


class WorldCupExecutor:
    BASE = 'https://mcs-mimp-web.sf-express.com/mcs-mimp'
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 mediaCode=SFEXPRESSAPP-iOS-ML',
        'channel': WORLD_CUP_CHANNEL,
        'platform': WORLD_CUP_PLATFORM,
    }

    def __init__(self, http: SFHttpClient, logger: Logger, user_id: str):
        self.http = http
        self.logger = logger
        self.user_id = user_id

    def _post(self, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
        return self.http.request(f'{self.BASE}{path}', data or {}, self.HEADERS)

    def _error(self, action: str, resp: Optional[Dict]):
        message = resp.get('errorMessage', '无响应') if resp else '无响应'
        error_code = resp.get('errorCode') if resp else None
        code_text = f'[{error_code}]' if error_code else ''
        self.logger.info(f'世界杯{action}失败{code_text}: {message}')

    def _assist(self):
        target = WORLD_CUP_ASSIST_ID.strip()
        if not target:
            self.logger.info('世界杯未配置助力 ID，跳过')
            return
        if target == self.user_id:
            self.logger.info('世界杯当前账号为助力目标，跳过自助')
            return
        resp = self._post(
            '/commonPost/~memberNonactivity~worldCupIndexService~index',
            {'inviteType': 1, 'inviteUserId': target},
        )
        if resp and resp.get('success'):
            self.logger.success(f'世界杯助力主账号 {target[:8]}... 成功')
        else:
            self._error('助力', resp)

    def _daily_gift(self, result: Dict[str, Any]):
        data = {'cityCode': WORLD_CUP_CITY_CODE}
        resp = self._post('/commonPost/~memberNonactivity~worldCupDailyService~getDailyGiftStatus', data)
        if not (resp and resp.get('success')):
            self._error('查询每日礼物', resp)
            return
        status = resp.get('obj') or {}
        if status.get('received'):
            self.logger.info('世界杯每日礼物今日已领取')
            return
        if not status.get('canReceive'):
            self.logger.info('世界杯每日礼物当前不可领取')
            return
        resp = self._post('/commonPost/~memberNonactivity~worldCupDailyService~receiveDailyGift', data)
        if resp and resp.get('success'):
            result['daily_gift'] = True
            self.logger.success('世界杯每日礼物领取成功')
        else:
            self._error('领取每日礼物', resp)

    def _tasks(self, result: Dict[str, Any]):
        task_data = {'activityCode': WORLD_CUP_ACTIVITY_CODE, 'channelType': WORLD_CUP_PLATFORM}
        resp = self._post('/commonPost/~memberNonactivity~activityTaskService~taskList', task_data)
        if not (resp and resp.get('success')):
            self._error('查询任务', resp)
            return
        tasks = resp.get('obj') or []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            if not is_safe_world_cup_task(task):
                continue
            name = str(task.get('taskName') or '未知任务')
            status = task.get('status')
            try:
                status = int(status)
            except (TypeError, ValueError):
                pass
            rest_finish = int(task.get('restFinishTime') or 0)
            if status == 3 or (status == 1 and rest_finish <= 0):
                self.logger.info(f'世界杯任务已完成: {name}')
                continue
            finish = self._post(
                '/commonPost/~memberEs~taskRecord~finishTask',
                {'taskCode': task.get('taskCode')},
            )
            if finish and finish.get('success') and finish.get('obj') is not False:
                result['tasks_completed'] += 1
                self.logger.success(f'世界杯任务完成: {name}')
            else:
                self._error(f'完成任务[{name}]', finish)
            time.sleep(1)

        reward = self._post(
            '/commonPost/~memberNonactivity~worldCupTaskService~fetchTaskReward',
            task_data,
        )
        if not (reward and reward.get('success')):
            self._error('领取任务奖励', reward)
            return
        received = (reward.get('obj') or {}).get('receivedAccountList') or []
        if received:
            text = ', '.join(f"{x.get('currency', '')} x{x.get('amount', 0)}" for x in received)
            self.logger.success(f'世界杯任务奖励: {text}')
        else:
            self.logger.info('世界杯暂无新任务奖励')

    def _game(self, result: Dict[str, Any]):
        resp = self._post('/commonPost/~memberNonactivity~worldCupGameService~index')
        if not (resp and resp.get('success')):
            self._error('查询射门游戏', resp)
            return
        game = resp.get('obj') or {}
        current_level = int(game.get('curLevel') or 1)
        reward_levels = [
            level for level in game.get('levelList') or []
            if int(level.get('rewardCoins') or 0) > 0
        ]
        if not reward_levels:
            self.logger.info('世界杯射门今日奖励已领取')
            return
        for level in reward_levels:
            level_no = int(level.get('level') or 0)
            if not level_no or level_no < current_level:
                continue
            target = int(level.get('target') or 0)
            passed = self._post(
                '/commonPost/~memberNonactivity~worldCupGameService~passReport',
                {'level': level_no, 'shotNum': target},
            )
            if not (passed and passed.get('success')):
                self._error(f'上报第{level_no}关', passed)
                break
            coin_num = int((passed.get('obj') or {}).get('coinNum') or 0)
            result['levels_passed'] += 1
            result['game_coins'] += coin_num
            self.logger.success(f'世界杯射门第{level_no}关完成，金币+{coin_num}')
            time.sleep(1)

    def _bet_status(self) -> Optional[Dict]:
        resp = self._post('/commonPost/~memberNonactivity~worldCupMatchService~betStatus')
        if resp and resp.get('success'):
            return resp.get('obj') or {}
        self._error('查询竞猜', resp)
        return None

    def _bet(self, result: Dict[str, Any]):
        status = self._bet_status()
        if status is None:
            return
        balance = int((status.get('currentAccount') or {}).get('balance') or 0)
        bet_coin = max(10, int(WORLD_CUP_BET_COIN))
        pending = [
            match for match in status.get('matchList') or []
            if match.get('matchStatus') == 'Fixture' and match.get('recordStatus', 0) == 0
        ]
        for match in pending:
            if balance < bet_coin:
                break
            bet_result = random.randint(0, 2)
            resp = self._post(
                '/commonPost/~memberNonactivity~worldCupMatchService~placeBet',
                {
                    'matchId': match.get('matchId'),
                    'betResult': bet_result,
                    'betCoin': bet_coin,
                },
            )
            if resp and resp.get('success'):
                balance -= bet_coin
                result['bets_placed'] += 1
                self.logger.success(f"世界杯竞猜已下注: {match.get('teamAName', '?')} vs {match.get('teamBName', '?')}")
            else:
                self._error('竞猜下注', resp)
            time.sleep(1)

    def _settle(self, result: Dict[str, Any]):
        resp = self._post('/commonPost/~memberNonactivity~worldCupMatchService~settleBet')
        if not (resp and resp.get('success')):
            self._error('结算竞猜', resp)
            return
        settled = resp.get('obj') or []
        result['settle_pnl'] = sum(
            (item.get('betWinCoin') or 0) - (item.get('betCoin') or 0)
            for item in settled
        )
        if settled:
            self.logger.info(f"世界杯竞猜结算: {result['settle_pnl']:+}")

    def _refresh_balance(self, result: Dict[str, Any]):
        status = self._bet_status()
        if status is None:
            return
        account = status.get('currentAccount') or {}
        result['balance'] = int(account.get('balance') or 0)
        result['total_amount'] = int(account.get('totalAmount') or 0)
        self.logger.points(result['balance'], '世界杯当前金币')

    def run(self) -> Dict[str, Any]:
        result = {
            'daily_gift': False,
            'tasks_completed': 0,
            'levels_passed': 0,
            'game_coins': 0,
            'bets_placed': 0,
            'settle_pnl': 0,
            'balance': 0,
            'total_amount': 0,
        }
        self.logger.info('━━━ 世界杯活动 ━━━')
        self._assist()
        index = self._post('/commonPost/~memberNonactivity~worldCupIndexService~index')
        if not (index and index.get('success')):
            self._error('查询首页', index)
            return result
        info = index.get('obj') or {}
        if info.get('acStartTime') or info.get('acEndTime'):
            self.logger.info(f"世界杯活动周期: {info.get('acStartTime', '')} ~ {info.get('acEndTime', '')}")

        self._daily_gift(result)
        self._tasks(result)
        if WORLD_CUP_ENABLE_GAME:
            self._game(result)
        if ENABLE_WORLD_CUP_BET:
            self._bet(result)
        else:
            self.logger.info('世界杯随机下注已关闭(配置区 ENABLE_WORLD_CUP_BET=True 可开启)')
        if WORLD_CUP_ENABLE_SETTLE:
            self._settle(result)
        self._refresh_balance(result)
        return result


# ==================== 账号执行 ====================
def run_account(account_raw: str, index: int) -> Dict[str, Any]:
    logger = Logger()
    if '#' in account_raw and (':' in account_raw.split('#')[-1]):
        last_hash = account_raw.rfind('#')
        account_url = account_raw[:last_hash].strip()
        fixed_proxy = account_raw[last_hash + 1:].strip()
    else:
        account_url = account_raw
        fixed_proxy = ""
    decoded_account = unquote(account_url)
    http = SFHttpClient(fixed_proxy)
    login_success = False
    phone = ''
    user_id = ''
    for attempt in range(MAX_PROXY_RETRIES):
        if attempt > 0:
            http = SFHttpClient(fixed_proxy)
        success, user_id, phone = http.login(account_url)
        if success:
            login_success = True
            break
        time.sleep(2)
    if not login_success:
        logger.error(f'账号{index + 1} 登录失败')
        ck_invalid = 'sessionid=' in decoded_account.lower() or '_login_' in decoded_account.lower()
        return {'success': False, 'phone': '', 'index': index,
                'points_before': 0, 'points_after': 0, 'points_earned': 0,
                'member_day_prizes': [], 'world_cup': {},
                'ck_invalid': ck_invalid, 'fail_reason': 'CK失效了' if ck_invalid else '登录失败'}
    masked = phone[:3] + "****" + phone[7:] if len(phone) >= 7 else phone
    logger.success(f'账号{index + 1}: 【{masked}】登录成功 | 🌐 {http.proxy_display}')
    time.sleep(random.uniform(1, 3))
    result = {
        'success': True, 'phone': phone, 'index': index,
        'points_before': 0, 'points_after': 0, 'points_earned': 0,
        'member_day_prizes': [], 'world_cup': {},
        'ck_invalid': False, 'fail_reason': '',
    }
    # 日常积分任务
    if ENABLE_DAILY_TASK:
        logger.info('━━━ 日常积分任务 ━━━')
        daily = DailyTaskExecutor(http, logger, user_id)
        daily.dual_sign_in()
        time.sleep(1)
        sign_ok, sign_err = daily.sign_in()
        if not sign_ok and '活动太火爆' in sign_err:
            for retry in range(3):
                logger.warning(f'签到IP问题，重试({retry + 1}/3)...')
                time.sleep(2)
                http = SFHttpClient(fixed_proxy)
                s, user_id, phone = http.login(account_url)
                if s:
                    daily.http = http
                    daily.user_id = user_id
                    sign_ok, sign_err = daily.sign_in()
                    if sign_ok or '活动太火爆' not in sign_err:
                        break
        pb, pa = daily.run()
        result['points_before'] = pb
        result['points_after'] = pa
        result['points_earned'] = pa - pb
    # 会员日活动 (每月26-28号)
    if ENABLE_MEMBER_DAY:
        current_day = datetime.now().day
        if 26 <= current_day <= 28:
            logger.info('━━━ 会员日活动 ━━━')
            md = MemberDayExecutor(http, logger, user_id)
            md_result = md.run()
            result['member_day_prizes'] = md_result.get('lottery_prizes', [])
        else:
            logger.info('⏰ 未到会员日(26-28号)，跳过')
    if ENABLE_WORLD_CUP:
        if world_cup_active():
            result['world_cup'] = WorldCupExecutor(http, logger, user_id).run()
        else:
            logger.info('⏰ 不在世界杯活动期(2026.07.02-07.20)，跳过')
    if http.ck_invalid:
        logger.error(f'账号{index + 1} CK失效了')
        result['success'] = False
        result['ck_invalid'] = True
        result['fail_reason'] = http.ck_invalid_message or 'CK失效了'
    return result


# ==================== 主程序 ====================
def main():
    env_name = 'sfsyUrl'
    env_value = os.getenv(env_name)
    if not env_value:
        print(f"❌ 未找到环境变量 {env_name}")
        return
    account_list = [u.strip() for u in env_value.split('&') if u.strip()]
    if not account_list:
        print(f"❌ 环境变量 {env_name} 为空")
        return
    random.shuffle(account_list)
    task_map = {
        "日常任务": ENABLE_DAILY_TASK,
        "会员日": ENABLE_MEMBER_DAY,
        "世界杯": ENABLE_WORLD_CUP,
    }
    enabled = [f"{k}✓" for k, v in task_map.items() if v]
    print("=" * 60)
    print("🎉 顺丰速运自动任务 v1.1.1")
    print("👨‍💻 From: YaoHuo8648")
    print(f"📱 共 {len(account_list)} 个账号")
    print(f"⚙️ 并发: {CONCURRENT_NUM} | 📋 {' '.join(enabled)}")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if PROXY_API_URL:
        _log_global(f"🔌 代理已开启: {PROXY_API_URL[:40]}...")
    print("=" * 60)
    all_results = []
    if CONCURRENT_NUM <= 1:
        for idx, raw in enumerate(account_list):
            result = run_account(raw, idx)
            all_results.append(result)
            if idx < len(account_list) - 1:
                time.sleep(2)
    else:
        with ThreadPoolExecutor(max_workers=CONCURRENT_NUM) as pool:
            futures = {pool.submit(run_account, raw, idx): idx for idx, raw in enumerate(account_list)}
            for f in as_completed(futures):
                all_results.append(f.result())
    all_results.sort(key=lambda x: x['index'])
    # 汇总
    print(f"\n{'='*70}")
    print("📊 执行汇总")
    print("=" * 70)
    total_earned = 0
    show_world_cup = ENABLE_WORLD_CUP and world_cup_active()
    total_world_cup_balance = 0
    for r in all_results:
        phone = r['phone'][:3] + "****" + r['phone'][7:] if r.get('phone') and len(r['phone']) >= 7 else r.get('phone', '未登录')
        earned = r.get('points_earned', 0)
        total_earned += earned
        world_cup = r.get('world_cup') or {}
        total_world_cup_balance += world_cup.get('balance', 0)
        if r.get('ck_invalid'):
            print(f"❌ {phone}: CK失效了")
        elif not r['success']:
            print(f"❌ {phone}: 登录失败")
        else:
            parts = [f"积分+{earned}"]
            md_prizes = r.get('member_day_prizes', [])
            if md_prizes:
                parts.append(f"会员日: {', '.join(md_prizes)}")
            if show_world_cup:
                parts.append(f"世界杯金币{world_cup.get('balance', 0)}")
                if world_cup.get('game_coins'):
                    parts.append(f"射门+{world_cup.get('game_coins')}")
                if world_cup.get('tasks_completed'):
                    parts.append(f"世界杯任务{world_cup.get('tasks_completed')}")
                if world_cup.get('daily_gift'):
                    parts.append('世界杯礼物✓')
                if world_cup.get('bets_placed'):
                    parts.append(f"竞猜{world_cup.get('bets_placed')}场")
            print(f"✅ {phone}: {' | '.join(parts)}")
    print("-" * 70)
    total_parts = [f"📱 总账号: {len(all_results)}", f"💰 总积分+{total_earned}"]
    if show_world_cup:
        total_parts.append(f"世界杯金币{total_world_cup_balance}")
    print(" | ".join(total_parts))
    print("=" * 70)
    print("🎊 执行完成!")
    push_lines = []
    for r in all_results:
        phone = r['phone'][:3] + "****" + r['phone'][7:] if r.get('phone') and len(r['phone']) >= 7 else r.get('phone', '未登录')
        if r.get('ck_invalid'):
            push_lines.append(f"❌ {phone}: CK失效了")
        elif not r['success']:
            push_lines.append(f"❌ {phone}: 登录失败")
        else:
            earned = r.get('points_earned', 0)
            parts = [f"积分+{earned}"]
            md_prizes = r.get('member_day_prizes', [])
            if md_prizes:
                parts.append(f"会员日: {', '.join(md_prizes)}")
            world_cup = r.get('world_cup') or {}
            if show_world_cup:
                parts.append(f"世界杯金币{world_cup.get('balance', 0)}")
                if world_cup.get('game_coins'):
                    parts.append(f"射门+{world_cup.get('game_coins')}")
                if world_cup.get('tasks_completed'):
                    parts.append(f"世界杯任务{world_cup.get('tasks_completed')}")
                if world_cup.get('daily_gift'):
                    parts.append('世界杯礼物✓')
            push_lines.append(f"✅ {phone}: {' | '.join(parts)}")
    push_lines.append(" | ".join(total_parts))
    notify_content = "\n".join(push_lines)
    if PUSH_SWITCH == "1" and notify_content:
        print("📤 准备推送消息...")
        try:
            if notify_send:
                notify_send("顺丰速运自动任务", notify_content)
                print("✅ 推送发送成功")
            else:
                print("⚠️ 未找到notify模块，无法推送")
        except Exception as e:
            print(f"❌ 推送发送失败: {e}")
    elif PUSH_SWITCH == "0":
        print("ℹ️ 推送开关未开启 (SFSY_PUSH=0)")


if __name__ == '__main__':
    main()
