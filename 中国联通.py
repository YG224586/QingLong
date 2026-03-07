# -*- coding: utf-8 -*-
"""
中国联通 Python 版 v1.0.2

包含以下功能:
1. 首页签到 (话费红包/积分)
2. 联通祝福 (各类抽奖)
3. 天天领现金 (每日打卡/立减金)
4. 权益超市 (任务/抽奖/浇水/领奖/全局库存缓存)
5. 安全管家 (日常任务/积分领取)
6. 联通云盘 (签到/AI互动/文件上传)
7. 联通阅读 (自动获取书籍/心跳阅读/抽奖/查红包)
8. 联通爱听 (积分任务/自动签到/阅读挂机/分享任务)
9. 沃云手机 (签到/任务/抽奖)
10. 区域专区 (自动识别新疆/河南执行特有任务)

更新说明:

### 20260301
v1.0.2:
- 🎛️ **全局总开关**：新增 globalConfig 配置字典，可一键 开/关 各功能模块。
- 🔧 **设备ID控制**：新增 refresh_device_id 选项，可选强制刷新或使用缓存设备ID。
- 📊 **启动日志优化**：启动时动态打印各模块开关状态及权益超市子开关详情。
- ⏱️ **智能冷却**：阅读/爱听均关闭时自动跳过120秒冷却等待。
- 🗑️ **移除失效活动**：删除已下架的云盘春节拼图活动代码（约565行）。
- 🔧 **修复模拟阅读**：补齐 addReadTime 缺失的用户参数，增强嵌套响应解析。
- 🔧 **修复安全管家**：getTicketByNative_sec 加入代理故障转移，避免代理失效时跳过全部任务。
- ⏱️ **阅读冷却等待**：阅读专区与爱听任务间增加120秒间隔，适配联通2分钟阅读冷却限制。

### 20260217
v1.0.1:
- 📝 **文档完善**: 迁移 JS 版头部说明，统一文档格式。
- 🧹 **代码清理**: 全面审查并移除冗余注释，优化代码结构。

配置说明:
1. 账号变量 (chinaUnicomCookie):
   赋值方式有三种:
   a. 填账号密码 (自动获取Token - 推荐):
      export chinaUnicomCookie="18600000000#123456"
   b. 填Token#AppId (免密模式 - 推荐):
      export chinaUnicomCookie="a3e4c1ff2xxxxxxxxx#912d30xxxxxx"
   c. 仅填Token (旧模式):
      export chinaUnicomCookie="a3e4c1ff2xxxxxxxxx"
   (多账号用 & 或 换行 隔开)

2. 代理设置 (可选):
   export UNICOM_PROXY_API="你的代理提取链接" (支持 JSON/TXT 格式，自动识别)
   export UNICOM_PROXY_TYPE="http" (可选 http 或 socks5，默认 http)

3. 特殊功能设置:
   export UNICOM_GRAB_AMOUNT="5"          : (可选) 抢兑面额 (默认5，自动匹配含"5元"或"5话费"的奖品)
   export UNICOM_GRAB_URL="https://..."   : (可选) 自定义抢兑接口地址
   export UNICOM_TEST_MODE="query"        : (可选) 仅查询模式，跳过任务执行只查询资产

定时规则建议 (Cron):
0 58 9,17 * * * (抢兑专用: 需 sign_config.run_grab_coupon=True，建议提前2分钟启动，脚本自动精准等待)
0 7,20 * * * (推荐：每天早晚7点/20点各跑一次，覆盖绝大部分签到任务)
"""
import os
import sys
import json
import time
import random
import re
import hashlib
import hmac
import base64
import logging
import requests
import uuid
import string
from datetime import datetime
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass
from urllib.parse import urlparse, parse_qs, urlencode, unquote, quote
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad
# ========================================
# 全局配置 (globalConfig)
# true=开启, false=关闭
# ========================================
globalConfig = {
    # --- 1. 功能总开关 (True=开启, False=关闭) ---
    "enable_sign": True,          # 首页签到 (🔺总开关, 含签到/任务/抢话费券)
    "enable_ttlxj": True,         # 天天领现金
    "enable_ltzf": True,          # 联通祝福
    "enable_woread": True,        # 联通阅读
    "enable_security": True,      # 安全管家
    "enable_ltyp": True,          # 联通云盘
    "enable_market": True,        # 权益超市 (🔺总开关, 必须开启内部功能才能运行)
    "enable_aiting": True,        # 联通爱听
    "enable_wostore": True,       # 沃云手机
    "enable_regional": True,      # 区域专区

    # --- ✅ 签到区内部细分开关 ---
    "sign_config": {
        "run_grab_coupon": False, # False = 关闭抢话费券 (True=开启抢兑, 需配合 UNICOM_GRAB_AMOUNT 设置面额)
    },

    # --- 🛒 权益超市内部细分开关 (按需修改到这里) ---
    "market_config": {
        "run_water": True,        # False = 关闭浇水
        "run_task": True,         # False = 关闭做任务(浏览/分享)
        "run_draw": True,         # True  = 开启抽奖
        "run_claim": True,       # True  = 开启自动领奖(建议开启, 不领白不领)
    },

    # --- 2. 设备ID配置 ---
    "refresh_device_id": False,   # False:使用缓存ID, True:强制刷新
}
COMMON_CONSTANTS = {
    "UA": "Dalvik/2.1.0 (Linux; U; Android 12; Mi 10 Pro MIUI/21.11.3);unicom{version:android@11.0802}",
    "MARKET_UA": "Dalvik/2.1.0 (Linux; U; Android 12; Mi 10 Pro MIUI/21.11.3);unicom{version:android@11.0802}",
    "APP_VERSION": "android@11.0802",
}
WOCARE_CONSTANTS = {
	"serviceLife": "wocareMBHServiceLife1",
	"anotherApiKey": "beea1c7edf7c4989b2d3621c4255132f",
	"anotherEncryptionKey": "f4cd4ffeb5554586acf65ba7110534f5",
	"minRetries": "1"
}
WOCARE_ACTIVITIES = [
	{"name": "星座配对", "id": 2},
	{"name": "大转盘", "id": 3},
	{"name": "盲盒抽奖", "id": 4}
]
AITING_BASE_URL = "https://pcc.woread.com.cn"
AITING_SIGN_KEY_APPKEY = "7ZxQ9rT3wE5sB2dF"
AITING_SIGN_KEY_API = "woread!@#qwe1234"
AITING_SIGN_KEY_REQUERTID = "46iCw24ewAZbNkK6"
AITING_CLIENT_KEY = "1"
AITING_AES_KEY = "j2K81755sxV12wFx"
AITING_AES_IV = "16-Bytes--String"
WOREAD_KEY = "woreadst^&*12345"
ADDREADTIME_AES_KEY = "UNS#READDAY39COM"
GRAB_AMOUNT = os.environ.get("UNICOM_GRAB_AMOUNT", "5")
GRAB_URL = os.environ.get("UNICOM_GRAB_URL", "https://act.10010.com/SigninApp/convert/prizeConvert")
UNICOM_TOKEN_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unicom_token_cache.json")
if "UNICOM_PROXY_API" not in os.environ:
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
LOGIN_PUB_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDc+CZK9bBA9IU+gZUOc6FUGu7yO9WpTNB0PzmgFBh96Mg1WrovD1oqZ+eIF4LjvxKXGOdI79JRdve9NPhQo07+uqGQgE4imwNnRx7PFtCRryiIEcUoavuNtuRVoBAm6qdB0SrctgaqGfLgKvZHOnwTjyNqjBUxzMeQlEC2czEMSwIDAQAB
-----END PUBLIC KEY-----"""

def mask_str(s):
    try:
        s = str(s)
        if len(s) == 11 and s.isdigit():
            return s[:3] + "****" + s[7:]
        elif s.startswith("enc_"):
            return s
        elif len(s) > 11:
            return s[:6] + "******" + s[-6:]
        return s
    except:
        return s

class FailoverSession:
    """包装 requests.Session，自动为所有请求添加代理故障转移"""
    RETRIABLE_KEYWORDS = ("Max retries exceeded", "timed out", "connection", "SOCKS", "ProxyError", "ConnectionError")

    def __init__(self, session, owner):
        self._session = session
        self._owner = owner  # UserService 实例引用

    def __getattr__(self, name):
        return getattr(self._session, name)

    def _should_failover(self, err_msg):
        if not os.environ.get("UNICOM_PROXY_API"):
            return False
        err_lower = err_msg.lower()
        return any(kw.lower() in err_lower for kw in self.RETRIABLE_KEYWORDS)

    def request(self, method, url, **kwargs):
        try:
            return self._session.request(method, url, **kwargs)
        except Exception as e:
            if self._should_failover(str(e)):
                self._owner.log(f"⚠️ [自动故障转移] {url} 请求异常: {e}")
                self._owner.failover_proxy()
                return self._session.request(method, url, **kwargs)
            raise

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

class UserService:
    def __init__(self, index, config_str):
        self.index = index
        self.valid = False
        self.notify_logs = []
        raw_session = requests.Session()
        import socket

        class SourceAddressAdapter(HTTPAdapter):

            def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
                pool_kwargs['source_address'] = ('0.0.0.0', 0)
                super(SourceAddressAdapter, self).init_poolmanager(connections, maxsize, block, **pool_kwargs)

            def get_connection(self, url, proxies=None):
                return super(SourceAddressAdapter, self).get_connection(url, proxies)
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = SourceAddressAdapter(max_retries=retries)
        raw_session.mount('http://', adapter)
        raw_session.mount('https://', adapter)
        raw_session.headers.update({
            "User-Agent": COMMON_CONSTANTS["UA"],
            "Connection": "keep-alive"
        })
        raw_session.verify = False
        import urllib3
        urllib3.disable_warnings()
        self.session = FailoverSession(raw_session, self)
        self.account_mobile = ""
        self.mobile = ""
        self.account_password = ""
        self.token_online = ""
        self.token_refresh = ""
        self.cookie = ""
        self.appId = ""
        self.city_info = []
        self.last_read_submission_time = 0
        if globalConfig.get("refresh_device_id", False):
            self.uuid = str(uuid.uuid4()).replace('-', '')
        else:
            self.uuid = os.environ.get("chinaUnicomUuid") or str(uuid.uuid4()).replace('-', '')
        self.unicomTokenId = self.random_string(32)
        self.tokenId_cookie = "chinaunicom-" + self.random_string(32, string.ascii_uppercase + string.digits)
        self.ecs_token = ""
        self.rptId = ""
        self.init_account(config_str)

    def _parse_proxy_response(self, text):
        """解析代理API响应，支持JSON和文本格式，提取ip/port/user/pass"""
        text = text.strip()

        def extract(d):
            if not d or not d.get('ip') or not d.get('port'):
                return None
            return {
                'ip': str(d['ip']),
                'port': int(d['port']),
                'user': str(d.get('account') or d.get('user') or ''),
                'pass': str(d.get('password') or d.get('pass') or '')
            }
        try:
            json_start = text.find('{')
            json_end = text.rfind('}')
            if json_start != -1 and json_end != -1:
                data = json.loads(text[json_start:json_end + 1])
                if data.get('ip') and data.get('port'):
                    return extract(data)
                if data.get('data'):
                    inner = data['data']
                    if isinstance(inner, dict) and inner.get('list') and isinstance(inner['list'], list) and len(inner['list']) > 0:
                        return extract(inner['list'][0])
                    if isinstance(inner, list) and len(inner) > 0:
                        return extract(inner[0])
                    if isinstance(inner, dict) and inner.get('ip'):
                        return extract(inner)
                if data.get('result') and isinstance(data['result'], dict) and data['result'].get('ip'):
                    return extract(data['result'])
        except:
            pass
        m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[:\s\t]+(\d{1,5})', text)
        if m:
            return {'ip': m.group(1), 'port': int(m.group(2)), 'user': '', 'pass': ''}
        return None

    def configure_proxy(self):
        proxy_api = os.environ.get("UNICOM_PROXY_API")
        if not proxy_api:
            return
        proxy_type = os.environ.get("UNICOM_PROXY_TYPE", "http").lower()
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                if attempt > 1:
                    self.log(f"🔄 [第{attempt}次] 重试获取代理IP ({proxy_type})...")
                    time.sleep(2)
                else:
                    self.log(f"正在获取代理IP (模式: {proxy_type})...")
                res = requests.get(proxy_api, timeout=10)
                if res.status_code != 200:
                    self.log(f"⚠️ 获取代理失败: HTTP {res.status_code}")
                    continue
                proxy_info = self._parse_proxy_response(res.text)
                if not proxy_info:
                    preview = res.text[:100] + "..." if len(res.text) > 100 else res.text
                    self.log(f"❌ 提取失败: 无法识别代理格式 (内容: {preview})")
                    continue
                ip, port = proxy_info['ip'], proxy_info['port']
                user, pwd = proxy_info['user'], proxy_info['pass']
                if user and pwd:
                    proxy_url = f"{proxy_type}://{quote(user)}:{quote(pwd)}@{ip}:{port}"
                    log_msg = f"{proxy_type}://***:***@{ip}:{port}"
                else:
                    proxy_url = f"{proxy_type}://{ip}:{port}"
                    log_msg = proxy_url
                self.log(f"🔍 提取成功: {log_msg}")
                test_proxies = {"http": proxy_url, "https": proxy_url}
                try:
                    requests.get("https://www.baidu.com", proxies=test_proxies, timeout=3)
                    self.session.proxies.update(test_proxies)
                    self.log("✅ 代理连通性测试通过")
                    return
                except Exception as te:
                    self.log(f"⚠️ 代理测试失败: {te}")
            except Exception as e:
                self.log(f"❌ 请求代理API异常: {e}")
        self.log(f"🚫 重试{max_retries}次均失败，回退至本地IP")

    def failover_proxy(self):
        proxy_api = os.environ.get("UNICOM_PROXY_API")
        if not proxy_api:
            return False
        self.log("⚠️ [故障转移] 检测到网络不稳定，正在检查当前代理是否存活...")
        try:
            requests.get("https://www.baidu.com", proxies=self.session.proxies, timeout=3)
            self.log("✅ [故障转移] 经测试当前IP仍有效，继续复用，暂不提取新IP。")
            time.sleep(1)
            return True
        except Exception as e:
            self.log(f"❌ [故障转移] 当前代理已失效 ({e})，准备更换新IP...")
        time.sleep(2)
        self.configure_proxy()
        return True

    def init_account(self, config_str):
        parts = config_str.split('#')
        if len(parts) >= 2 and len(parts[0]) == 11 and parts[0].isdigit() and len(parts[1]) < 50:
             self.account_mobile = parts[0]
             self.account_password = parts[1]
        else:
            self.token_online = parts[0].strip()
            if len(self.token_online) == 11 and self.token_online.isdigit():
                self.account_mobile = self.token_online
                self.token_online = "" # Reset, allow load_token_from_cache to fill it
                self.log(f"识别到纯手机号模式: {mask_str(self.account_mobile)}")
            if len(parts) > 1:
                 self.appId = parts[1].strip()
            if len(parts) > 2 and parts[2]:
                potential_mobile = parts[2].strip()
                if potential_mobile.isdigit() and len(potential_mobile)==11:
                    self.account_mobile = potential_mobile
        self.unicomTokenId = str(uuid.uuid4()).replace('-', '') # simplified
        self.tokenId_cookie = "chinaunicom-" + str(uuid.uuid4()).replace('-', '').upper() # simplified
        self.cookie_string = f"TOKENID_COOKIE={self.tokenId_cookie}; UNICOM_TOKENID={self.unicomTokenId}; sdkuuid={self.unicomTokenId}"
        self.update_session_cookies()

    def update_session_cookies(self):
        if self.cookie_string:
            cookies = {}
            for item in self.cookie_string.split(';'):
                if '=' in item:
                    k, v = item.split('=', 1)
                    cookies[k.strip()] = v.strip()
            self.session.cookies.update(cookies)
        extra_cookies = {}
        if self.token_online:
            extra_cookies['token_online'] = self.token_online
        if self.appId:
            extra_cookies['appId'] = self.appId
        if extra_cookies:
            self.session.cookies.update(extra_cookies)

    def log(self, msg, notify=False):
        prefix = f"账号[{self.index}]"
        full_msg = f"{prefix}{msg}"
        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] {full_msg}"
        print(log_line)
        if notify:
            self.notify_logs.append(str(msg))

    def rsa_encrypt(self, val):
        self.log(f"正在进行 RSA 加密...")
        try:
             random_str = ''.join(str(random.randint(0, 9)) for _ in range(6))
             text = str(val) + random_str
             data = text.encode('utf-8')
             key_pem = LOGIN_PUB_KEY.encode()
             recipient_key = RSA.import_key(key_pem)
             cipher_rsa = PKCS1_v1_5.new(recipient_key)
             enc_data = cipher_rsa.encrypt(data)
             return base64.b64encode(enc_data).decode('utf-8')
        except Exception as e:
            self.log(f"RSA加密失败: {str(e)}")
            return ""

    def generate_appid(self):

        def rnd(): return str(random.randint(0, 9))
        return (f"{rnd()}f{rnd()}af"
                f"{rnd()}{rnd()}ad"
                f"{rnd()}912d306b5053abf90c7ebbb695887bc"
                f"870ae0706d573c348539c26c5c0a878641fcc0d3e90acb9be1e6ef858a"
                f"59af546f3c826988332376b7d18c8ea2398ee3a9c3db947e2471d32a49") + rnd() + rnd()

    def unicom_login(self):
        self.log(f"正在使用账号 {mask_str(self.account_mobile)} 进行登录...")
        if not self.appId:
            self.appId = self.generate_appid()
            self.log(f"生成临时 AppId: {self.appId[:15]}...")
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            payload = {
                "version": COMMON_CONSTANTS["APP_VERSION"],
                "mobile": self.rsa_encrypt(self.account_mobile),
                "reqtime": timestamp,
                "deviceModel": "Android",
                "netWay": "Wifi",
                "isR4": "0",
                "password": self.rsa_encrypt(self.account_password),
                "appId": self.appId
            }
            url = "https://m.client.10010.com/mobileService/login.htm"
            res = self.session.post(url, data=payload)
            result = res.json()
            if result.get('code') in ['0', '0000']:
                if result.get('token_online'):
                    self.token_online = result['token_online']
                    self.log("✅ 登录接口验证通过")
                    return True
                else:
                    self.log("❌ 登录响应中未找到 token_online")
            else:
                self.log(f"❌ 登录失败: {result.get('desc')} (Code: {result.get('code')})")
        except Exception as e:
            self.log(f"❌ 登录过程异常: {str(e)}")
        return False

    def request(self, method, url, **kwargs):
        try:
            current_cookies = self.session.cookies.get_dict()
            if self.cookie_string:
                for item in self.cookie_string.split(';'):
                    if '=' in item:
                        k, v = item.split('=', 1)
                        current_cookies[k.strip()] = v.strip()
            cookie_header = "; ".join([f"{k}={v}" for k, v in current_cookies.items()])
            if cookie_header:
                if 'headers' not in kwargs:
                    kwargs['headers'] = {}
                kwargs['headers']['Cookie'] = cookie_header
            timeout = kwargs.get('timeout', 10)
            if 'timeout' in kwargs: del kwargs['timeout']
            response = self.session.request(method, url, timeout=timeout, **kwargs)
            if response.status_code >= 400:
                self.log(f"请求 {url} 返回状态码 {response.status_code}")
            return response
        except Exception as e:
            self.log(f"请求 {url} 异常: {str(e)}")
            return None

    def load_token_from_cache(self):
        if not self.account_mobile:
            return False
        if not os.path.exists(UNICOM_TOKEN_CACHE_PATH):
            return False
        try:
            with open(UNICOM_TOKEN_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            user_cache = cache.get(self.account_mobile)
            if user_cache and user_cache.get('token_online'):
                if (datetime.now().timestamp() * 1000) - user_cache.get('timestamp', 0) < 12 * 60 * 60 * 1000:
                    self.token_online = user_cache['token_online']
                    self.appId = user_cache.get('appId', self.appId)
                    self.city_info = user_cache.get('city_info', [])
                    self.update_session_cookies()
                    self.log(f"♻️ [缓存复用] 成功加载本地 Token ({user_cache.get('time')})")
                    return True
        except Exception as e:
            pass
        return False

    def save_token_to_cache(self):
        if not self.account_mobile:
            return
        cache = {}
        if os.path.exists(UNICOM_TOKEN_CACHE_PATH):
             try:
                with open(UNICOM_TOKEN_CACHE_PATH, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
             except: pass
        now = datetime.now()
        cache[self.account_mobile] = {
            "token_online": self.token_online,
            "appId": self.appId,
            "city_info": getattr(self, 'city_info', []),
            "cookieString": "",
            "timestamp": int(now.timestamp() * 1000),
            "time": now.strftime('%Y-%m-%d %H:%M:%S')
        }
        try:
            with open(UNICOM_TOKEN_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            self.log("💾 [缓存保存] Token 已写入本地文件")
        except Exception as e:
            self.log(f"❌ 保存缓存失败: {str(e)}")

    def get_city_info(self):
        try:
            url = "https://m.client.10010.com/mobileService/business/get/getCity"
            res = self.session.post(url, data={}, timeout=10).json()
            if res.get('code') == '200' and res.get('list'):
                 self.city_info = res.get('list')
                 return True
            return False
        except:
            return False

    def queryRemain(self):
        try:
            if not self.ecs_token:
                if not self.onLine():
                    self.log("❌ 无法获取 ecs_token，跳过查询")
                    return
            self.log("==== 资产查询 ====")
            self.log("正在查询套餐余量...")
            url = "https://m.client.10010.com/servicequerybusiness/balancenew/accountBalancenew.htm"
            headers = {
                "User-Agent": COMMON_CONSTANTS["MARKET_UA"],
                "Cookie": f"ecs_token={self.ecs_token}"
            }
            res = self.request("get", url, headers=headers)
            if not res: return
            result = res.json()
            if result.get('code') == '0000':
                current_balance = "0.00"
                real_time_fee = "0.00"
                if result.get('curntbalancecust'):
                    current_balance = str(result['curntbalancecust'])
                if result.get('realfeecust'):
                    real_time_fee = str(result['realfeecust'])
                self.log(f"💰 [资产-话费] 当前余额: {current_balance}元, 实时话费: {real_time_fee}元", notify=True)
                pkg_list = result.get('realTimeFeeSpecialFlagThree', [])
                if pkg_list and isinstance(pkg_list, list):
                    self.log(f"    📋 [套餐详情]:", notify=True)
                    for item in pkg_list:
                        sub_items = item.get('subItems', [])
                        if sub_items:
                            for sub in sub_items:
                                bill = sub.get('bill', {})
                                if bill:
                                    name = bill.get('integrateitem', '未知项')
                                    fee = bill.get('realfee', '0.00')
                                    self.log(f"       - {name}: {fee}元", notify=True)
            else:
                msg = result.get('desc') or result.get('msg') or "未知错误"
                self.log(f"套餐余量查询失败: {msg}")
        except Exception as e:
            self.log(f"queryRemain 异常: {str(e)}")

    def onLine(self):
        if not self.token_online:
             self.log("❌ 缺少 token_online，无法执行 onLine")
             return False
        try:
            url = "https://m.client.10010.com/mobileService/onLine.htm"
            data = {
                'isFirstInstall': '1',
                'netWay': 'Wifi',
                'version': 'android@11.0000',
                'token_online': self.token_online,
                'provinceChanel': 'general',
                'deviceModel': 'ALN-AL10',
                'step': 'dingshi',
                'androidId': '291a7deb1d716b5a',
                'reqtime': int(time.time() * 1000)
            }
            if self.appId:
                data['appId'] = self.appId
            res = self.request('post', url, data=data)
            if not res: return False
            result = res.json()
            code = result.get('code')
            if code == '0' or code == 0:
                self.valid = True
                desmobile = result.get('desmobile', '')
                if len(desmobile) == 11 and desmobile.isdigit():
                    self.account_mobile = desmobile
                    self.mobile = desmobile
                elif desmobile.startswith("enc_"):
                     if not self.account_mobile:
                          self.log("⚠️ 注意: 服务端返回了加密手机号且未配置本地手机号")
                self.log("登录成功")
                self.city_info = result.get('list', [])
                self.ecs_token = result.get('ecs_token')
                return True
            else:
                self.log(f"登录失败[{code}]: {result.get('msg')}")
                return False
        except Exception as e:
            self.log(f"onLine 异常: {str(e)}")
            return False

    def gettaskip(self):
        orderId = self.random_string(32).upper()
        try:
            url = "https://m.client.10010.com/taskcallback/topstories/gettaskip"
            data = {
                "mobile": self.account_mobile,
                "orderId": orderId
            }
            self.request("post", url, data=data)
        except Exception as e:
            pass
        return orderId

    def sign_getContinuous(self, is_query_only=False):
        try:
            url = "https://activity.10010.com/sixPalaceGridTurntableLottery/signin/getContinuous"
            params = {
                "taskId": "",
                "channel": "wode",
                "imei": self.uuid
            }
            res = self.request("get", url, params=params)
            if not res: return
            result = res.json()
            code = result.get('code')
            if code == "0000":
                todayIsSignIn = result.get('data', {}).get('todayIsSignIn', 'n')
                self.log(f"签到区今天{'已' if todayIsSignIn == 'y' else '未'}签到", notify=True)
                if todayIsSignIn == 'y':
                    pass
                else:
                    if not is_query_only:
                        time.sleep(1)
                        self.sign_daySign()
                    else:
                        self.log("签到区: [查询模式] 跳过自动打卡")
            else:
                self.log(f"签到区查询签到状态失败[{code}]: {result.get('desc', '')}")
        except Exception as e:
            self.log(f"sign_getContinuous 异常: {str(e)}")

    def sign_daySign(self):
        try:
            url = "https://activity.10010.com/sixPalaceGridTurntableLottery/signin/daySign"
            res = self.request("post", url, data={})
            if not res: return
            result = res.json()
            code = result.get('code')
            if code == "0000":
                data = result.get('data', {})
                msg = f"签到区签到成功: [{data.get('statusDesc', '')}]{data.get('redSignMessage', '')}"
                self.log(msg)
            elif code == "0002" and "已经签到" in result.get('desc', ''):
                self.log("签到区签到成功: 今日已完成签到！")
            else:
                self.log(f"签到区签到失败[{code}]: {result.get('desc', '')}")
        except Exception as e:
            self.log(f"sign_daySign 异常: {str(e)}")

    def sign_getTelephone(self, is_initial=False, silent=False):
        try:
            url = "https://act.10010.com/SigninApp/convert/getTelephone"
            res = self.request("post", url, data={})
            if not res: return None
            result = res.json()
            status = result.get('status')
            if status == "0000" and result.get('data'):
                tel_val = result['data'].get('telephone', 0)
                try:
                    current_amount = float(tel_val)
                except:
                    current_amount = 0.0
                if silent:
                    return current_amount
                if is_initial:
                    msg = f"签到区-话费红包: 运行前总额 {current_amount:.2f}元"
                    self.sign_initial_amount = current_amount
                else:
                    if hasattr(self, 'sign_initial_amount'):
                        increase = current_amount - self.sign_initial_amount
                        self.log(f"签到区-话费红包: 本次运行增加 {increase:.2f}元", notify=True)
                    msg = f"签到区-话费红包: 总额 {current_amount:.2f}元"
                    exp_val = result['data'].get('needexpNumber', 0)
                    try:
                        exp_num = float(exp_val)
                    except:
                        exp_num = 0.0
                    if exp_num > 0:
                        msg += f"，其中 {result['data'].get('needexpNumber', '0')}元 将于 {result['data'].get('month', '')}月底到期"
                self.log(msg, notify=not is_initial)
                return current_amount
            else:
                if not silent:
                    self.log(f"签到区查询话费红包失败[{status}]: {result.get('msg', '')}")
                return None
        except Exception as e:
            if not silent:
                self.log(f"sign_getTelephone 异常: {str(e)}")
            return None

    def sign_getTaskList(self):
        try:
            url = "https://activity.10010.com/sixPalaceGridTurntableLottery/task/taskList"
            headers = {"Referer": "https://img.client.10010.com/"}
            for i in range(30):
                res = self.request("get", url, params={"type": "2"}, headers=headers, timeout=10)
                if not res: return
                result = res.json()
                code = result.get('code')
                if code == "0329" or "火爆" in result.get('desc', ''):
                    self.log("签到区: 系统繁忙(0329)，停止后续尝试")
                    break
                if code != "0000":
                    self.log(f"签到区-任务中心: 获取任务列表失败[{code}]: {result.get('desc', '')}")
                    return
                tag_list = result.get('data', {}).get('tagList', []) or []
                task_list = result.get('data', {}).get('taskList', []) or []
                all_tasks = task_list + [t for tag in tag_list for t in tag.get('taskDTOList', [])]
                all_tasks = [t for t in all_tasks if t]
                if not all_tasks:
                    if i == 0: self.log("签到区-任务中心: 当前无任何任务。")
                    break
                do_task = next((t for t in all_tasks if t.get('taskState') == '1' and t.get('taskType') == '5'), None)
                if do_task:
                    self.log(f"签到区-任务中心: 开始执行任务 [{do_task.get('taskName')}]")
                    self.sign_doTaskFromList(do_task)
                    time.sleep(3)
                    continue
                claim_task = next((t for t in all_tasks if t.get('taskState') == '0'), None)
                if claim_task:
                    self.log(f"签到区-任务中心: 发现可领取奖励的任务 [{claim_task.get('taskName')}]")
                    self.sign_getTaskReward(claim_task.get('id'))
                    time.sleep(2)
                    continue
                if i == 0:
                    self.log("签到区-任务中心: 没有可执行或可领取的任务。")
                else:
                    self.log("签到区-任务中心: 所有任务处理完毕。")
                break
        except Exception as e:
            self.log(f"sign_getTaskList 异常: {str(e)}")

    def sign_doTaskFromList(self, task):
        try:
            if task.get('url') and task['url'] != '1' and task['url'].startswith('http'):
                 self.request("get", task['url'], headers={"Referer": "https://img.client.10010.com/"})
                 self.log(f"签到区-任务中心: 浏览页面 [{task.get('taskName')}]")
                 time.sleep(random.uniform(5, 7))
            orderId = self.gettaskip()
            url = "https://activity.10010.com/sixPalaceGridTurntableLottery/task/completeTask"
            params = {
                "taskId": task.get('id'),
                "orderId": orderId,
                "systemCode": "QDQD"
            }
            res = self.request("get", url, params=params)
            if not res: return
            result = res.json()
            code = result.get('code')
            if code == "0000":
                self.log(f"签到区-任务中心: ✅ 任务 [{task.get('taskName')}] 已完成")
            else:
                self.log(f"签到区-任务中心: ❌ 任务 [{task.get('taskName')}] 完成失败[{code}]: {result.get('desc', '未知错误')}")
        except Exception as e:
             self.log(f"sign_doTaskFromList 异常: {str(e)}")

    def sign_getTaskReward(self, task_id):
        try:
            url = "https://activity.10010.com/sixPalaceGridTurntableLottery/task/getTaskReward"
            res = self.request("get", url, params={"taskId": task_id})
            if not res: return
            result = res.json()
            code = result.get('code')
            if code == "0000":
                data = result.get('data', {})
                if data.get('code') == '0000':
                    self.log(f"签到区-领取奖励: [{data.get('prizeName', '')}] {data.get('prizeNameRed', '')}")
                else:
                    self.log(f"签到区-领取奖励失败[{data.get('code')}]: {result.get('desc') or data.get('desc')}")
            else:
                self.log(f"签到区-领取奖励失败[{code}]: {result.get('desc', '')}")
        except Exception as e:
            self.log(f"sign_getTaskReward 异常: {str(e)}")

    def sign_grabCoupon(self):
        sc = globalConfig.get("sign_config", {})
        if not sc.get("run_grab_coupon", False):
             return
        self.log(f"⚔️ [抢兑阶段] 正在检查目标: {GRAB_AMOUNT}元 话费券...")
        candidates = []
        try:
            url = "https://act.10010.com/SigninApp/new_convert/prizeList"
            headers = {"Origin": "https://img.client.10010.com"}
            res = self.request("post", url, headers=headers)
            if res:
                list_res = res.json()
                if list_res.get('status') == "0000":
                    details = list_res.get('data', {}).get('datails', {})
                    tab_items = details.get('tabItems', [])
                    self.log(f"📋 [调试] 共获取到 {len(tab_items)} 个场次数据")
                    for tab in tab_items:
                        products = tab.get('timeLimitQuanListData', [])
                        round_time_str = tab.get('time', '')
                        round_date = None
                        try:
                            if round_time_str and ":" in round_time_str:
                                now = datetime.now()
                                date_str = now.strftime('%Y/%m/%d')
                                full_time_str = f"{date_str} {round_time_str}"
                                if len(round_time_str) <= 8:
                                    round_date = datetime.strptime(full_time_str, "%Y/%m/%d %H:%M")
                                else:
                                    round_date = datetime.strptime(round_time_str, "%Y-%m-%d %H:%M:%S")
                        except:
                            pass
                        for item in products:
                            p_name = item.get('product_name', '')
                            if str(GRAB_AMOUNT) in p_name and ("元" in p_name or "话费" in p_name):
                                 self.log(f"      ✅ 发现目标: {p_name} (ID: {item.get('product_id')})")
                                 candidates.append({
                                     "id": item.get('product_id'),
                                     "name": p_name,
                                     "typeCode": item.get('type_code') or '0',
                                     "timeStr": round_time_str,
                                     "startTime": round_date,
                                     "itemData": item
                                 })
        except Exception as e:
            self.log(f"❌ 获取奖品列表失败: {str(e)}")
        if not candidates:
            self.log(f"⚠️ 未在任何场次中匹配到名为 '{GRAB_AMOUNT}元' 的奖品。")
            return
        now = datetime.now()
        best_candidate = None
        min_diff = float('inf')
        for cand in candidates:
            start_time = cand['startTime']
            if not start_time: continue
            diff = (start_time - now).total_seconds()
            score = 0
            if diff > 0:
                score = diff
            elif diff > -600:
                score = abs(diff) + 10000
            else:
                score = abs(diff) + 90000
            if score < min_diff:
                min_diff = score
                best_candidate = cand
        if not best_candidate:
            best_candidate = candidates[0]
        self.log(f"🎯 最终锁定场次: [{best_candidate['timeStr']}] {best_candidate['name']}")
        if best_candidate['startTime']:
            start_time = best_candidate['startTime']
            wait_seconds = (start_time - datetime.now()).total_seconds()
            if wait_seconds > 0:
                if wait_seconds > 300:
                    self.log(f"⏳ 距离开抢还有 {wait_seconds:.1f} 秒，大于5分钟，暂不等待。建议在临近时间(如提前2分钟)再运行脚本。")
                    return
                self.log(f"⏳ 正在等待开抢... (剩余 {wait_seconds:.1f} 秒)")
                while (best_candidate['startTime'] - datetime.now()).total_seconds() > 0.5:
                    time.sleep(0.5)
            else:
                 self.log(f"⚡ 当前时间已超过场次时间 {abs(wait_seconds):.1f}s，直接抢兑！")
        self.sign_grab_execute(best_candidate)

    def sign_grab_execute(self, candidate):
        for i in range(1, 6):
            self.log(f"🔥 [第{i}次冲击] 发起兑换请求...")
            try:
                data = {
                    "product_id": candidate['id'],
                    "typeCode": candidate['typeCode']
                }
                url = GRAB_URL
                headers = {
                    "Origin": "https://img.client.10010.com",
                    "Referer": "https://img.client.10010.com/",
                    "X-Requested-With": "com.sinovatech.unicom.ui"
                }
                res = self.request("post", url, data=data, headers=headers)
                if not res: continue
                result = res.json()
                uuid_val = result.get('data', {}).get('uuid')
                status = result.get('status')
                if status == "0000" and uuid_val:
                    self.log(f"📝 [提交成功] 获取到工单号: {uuid_val}，正在查询最终结果...")
                    check_url = "https://act.10010.com/SigninApp/convert/prizeConvertResult"
                    check_data = { "uuid": uuid_val }
                    check_res = self.request("post", check_url, data=check_data, headers=headers)
                    if not check_res: continue
                    final_res = check_res.json()
                    final_status = final_res.get('status')
                    if final_status == "0000":
                        self.log(f"🎉🎉🎉 [抢兑成功] 恭喜！已成功抢到目标奖品！ 🎉🎉🎉", notify=True)
                        return
                    else:
                        err_code = final_res.get('data', {}).get('errorCode', '')
                        msg = final_res.get('msg', '') or final_res.get('message', '未知原因')
                        detail_msg = final_res.get('data', {}).get('rightBtn', {}).get('name', '')
                        log_msg = f"💔 [抢兑失败] 状态: {final_status}"
                        if err_code: log_msg += f" | 错误码: {err_code}"
                        if detail_msg: log_msg += f" | 详情: {detail_msg}"
                        log_msg += f" | 提示: {msg}"
                        self.log(log_msg, notify=True)
                else:
                    self.log(f"📝 提交结果: {result.get('msg') or result.get('message') or json.dumps(result)}")
                time.sleep(0.2)
            except Exception as e:
                self.log(f"❌ 抢兑异常: {str(e)}")

    def get_wocare_body(self, apiCode, requestData={}):
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S') + str(int(datetime.now().microsecond / 1000)).zfill(3)
        encodedContent = base64.b64encode(json.dumps(requestData, separators=(',', ':')).encode('utf-8')).decode('utf-8')
        body = {
            "version": WOCARE_CONSTANTS["minRetries"],
            "apiCode": apiCode,
            "channelId": WOCARE_CONSTANTS["anotherApiKey"],
            "transactionId": timestamp + self.random_string(6, "0123456789"),
            "timeStamp": timestamp,
            "messageContent": encodedContent
        }
        params_array = []
        for key in sorted(body.keys()):
            params_array.append(f"{key}={body[key]}")
        params_array.append(f"sign={WOCARE_CONSTANTS['anotherEncryptionKey']}")
        sign_str = "&".join(params_array)
        body["sign"] = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
        return body

    def wocare_api(self, apiCode, requestData={}):
        try:
            url = f"https://wocare.unisk.cn/api/v1/{apiCode}"
            body = self.get_wocare_body(apiCode, requestData)
            res = self.request("post", url, data=body)
            if not res: return None
            result = res.json()
            if result.get("messageContent"):
                try:
                    content = result["messageContent"]
                    content = content.replace('\n', '').replace('\r', '').replace(' ', '')
                    content = content.replace('-', '+').replace('_', '/')
                    missing_padding = len(content) % 4
                    if missing_padding:
                        content += '=' * (4 - missing_padding)
                    try:
                        decoded_bytes = base64.b64decode(content)
                        decoded_str = decoded_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_str = decoded_bytes.decode('utf-8', errors='replace')
                    except Exception as e:
                        decoded_str = "{}"
                    try:
                        decoded = json.loads(decoded_str, strict=False)
                    except:
                        decoded_str = re.sub(r'[\x00-\x1f\x7f]', '', decoded_str)
                        try:
                            decoded = json.loads(decoded_str, strict=False)
                        except:
                            decoded = {}
                    if isinstance(decoded, dict):
                        if "data" in decoded:
                            result["data"] = decoded["data"]
                        else:
                            result["data"] = decoded
                        if "resultMsg" in decoded:
                            result["resultMsg"] = decoded["resultMsg"]
                        if "resultCode" in decoded:
                            result["resultCode"] = decoded["resultCode"]
                except Exception as e:
                    self.log(f"联通祝福: 解析返回失败: {str(e)}")
            return result
        except Exception as e:
            self.log(f"wocare_api 异常: {str(e)}")
            return None

    def wocare_getToken(self, ticket):
        try:
            url = "https://wocare.unisk.cn/mbh/getToken"
            params = {
                "channelType": WOCARE_CONSTANTS["serviceLife"],
                "type": "02",
                "ticket": ticket,
                "version": COMMON_CONSTANTS["APP_VERSION"],
                "timestamp": datetime.now().strftime('%Y%m%d%H%M%S') + str(int(datetime.now().microsecond / 1000)).zfill(3),
                "desmobile": self.account_mobile,
                "num": "0",
                "postage": self.random_string(32),
                "homePage": "home",
                "duanlianjieabc": "qAz2m",
                "userNumber": self.account_mobile
            }
            res = self.session.get(url, params=params, allow_redirects=False, timeout=15)
            if res.status_code == 302:
                location = res.headers.get("Location", "")
                if location:
                    parsed = urlparse(location)
                    sid = parse_qs(parsed.query).get("sid", [None])[0]
                    if not sid:
                        sid = parse_qs(parsed.query).get("uuid", [None])[0]
                        if sid:
                            self.log(f"联通祝福: 未找到sid，使用uuid替代: {sid}")
                    if sid:
                        self.wocare_sid = sid
                        return self.wocare_loginmbh()
                    else:
                        self.log(f"联通祝福: 没有获取到sid或uuid, Location: {location}")
                else:
                    self.log("联通祝福: 没有获取到location")
            else:
                self.log(f"联通祝福: 获取sid失败[{res.status_code}]")
        except Exception as e:
            self.log(f"wocare_getToken 异常: {str(e)}")
        return False

    def wocare_loginmbh(self):
        try:
            apiCode = "loginmbh"
            requestData = {
                "sid": self.wocare_sid,
                "channelType": WOCARE_CONSTANTS["serviceLife"],
                "apiCode": apiCode
            }
            result = self.wocare_api(apiCode, requestData)
            if not result: return False
            responseResult = result
            resultCode = responseResult.get("resultCode", "-1")
            if resultCode == "0000":
                self.wocare_token = responseResult.get("data", {}).get("token")
                self.log("联通祝福: 登录成功")
                return True
            else:
                msg = responseResult.get("resultMsg") or responseResult.get("resultDesc") or ""
                self.log(f"联通祝福: 登录失败[{resultCode}]: {msg}")
        except Exception as e:
            self.log(f"wocare_loginmbh 异常: {str(e)}")
        return False

    def wocare_getDrawTask(self, activity):
        try:
            apiCode = "getDrawTask"
            requestData = {
                "token": self.wocare_token,
                "channelType": WOCARE_CONSTANTS["serviceLife"],
                "type": activity["id"],
                "apiCode": apiCode
            }
            result = self.wocare_api(apiCode, requestData)
            responseResult = result if result else {}
            resultCode = responseResult.get("resultCode", "-1")
            if resultCode == "0000":
                taskList = responseResult.get("data", {}).get("taskList", []) or []
                if not taskList:
                    pass
                else:
                    self.log(f"联通祝福: [{activity['name']}] 查询到 {len(taskList)} 个任务")
                    for task in taskList:
                        ts = task.get("taskStatus")
                        if str(ts) == "0" or not ts:
                            self.wocare_completeTask(activity, task)
            else:
                msg = responseResult.get("resultMsg") or responseResult.get("resultDesc") or ""
                self.log(f"联通祝福: [{activity['name']}]查询任务失败[{resultCode}]: {msg}")
        except Exception as e:
            self.log(f"wocare_getDrawTask 异常: {str(e)}")

    def wocare_completeTask(self, activity, task, taskStep="1"):
        try:
            taskTitle = task.get("title", "")
            action = "领取任务" if taskStep == "1" else "完成任务"
            apiCode = "completeTask"
            requestData = {
                "token": self.wocare_token,
                "channelType": WOCARE_CONSTANTS["serviceLife"],
                "task": task.get("id"),
                "taskStep": taskStep,
                "type": activity["id"],
                "apiCode": apiCode
            }
            result = self.wocare_api(apiCode, requestData)
            responseResult = result if result else {}
            resultCode = responseResult.get("resultCode", "-1")
            if resultCode == "0000":
                self.log(f"联通祝福: {action}[{taskTitle}]成功")
                if taskStep == "1":
                    time.sleep(1)
                    self.wocare_completeTask(activity, task, "4")
            else:
                msg = responseResult.get("resultMsg") or responseResult.get("resultDesc") or ""
                self.log(f"联通祝福: [{activity['name']}]{action}[{taskTitle}]失败[{resultCode}]: {msg}")
        except Exception as e:
            self.log(f"wocare_completeTask 异常: {str(e)}")

    def wocare_getSpecificityBanner(self):
        try:
            apiCode = "getSpecificityBanner"
            requestData = {
                "token": self.wocare_token,
                "apiCode": apiCode
            }
            result = self.wocare_api(apiCode, requestData)
            responseResult = result if result else {}
            resultCode = responseResult.get("resultCode", "-1")
            if resultCode == "0000":
                bannerList = responseResult.get("data", []) or []
                if not bannerList:
                    self.log(f"联通祝福: 获取动态 Banner 列表为空，接口明细: {responseResult}")
                for banner in bannerList:
                    if str(banner.get("activityStatus")) == "0" and str(banner.get("isDeleted")) == "0":
                        self.wocare_getDrawTask(banner)
                        self.wocare_loadInit(banner)
            else:
                msg = responseResult.get("resultMsg") or responseResult.get("resultDesc", "")
                self.log(f"联通祝福: 进入活动失败[{resultCode}]: {msg}")
        except Exception as e:
            self.log(f"wocare_getSpecificityBanner 异常: {str(e)}")

    def wocare_loadInit(self, activity):
        try:
            apiCode = "loadInit"
            requestData = {
                "token": self.wocare_token,
                "channelType": WOCARE_CONSTANTS["serviceLife"],
                "type": activity["id"],
                "apiCode": apiCode
            }
            result = self.wocare_api(apiCode, requestData)
            responseResult = result if result else {}
            resultCode = responseResult.get("resultCode", "-1")
            if resultCode == "0000":
                responseData = responseResult.get("data", {}) or {}
                activeModuleGroupId = responseData.get("zActiveModuleGroupId")
                drawCount = 0
                aid = activity["id"]
                if aid == 2:
                    isPartake = responseData.get("data", {}).get("isPartake") or 0
                    if not isPartake:
                        drawCount = 1
                elif aid == 3:
                    drawCount = int(responseData.get("raffleCountValue", 0) or 0)
                elif aid == 4:
                    drawCount = int(responseData.get("mhRaffleCountValue", 0) or 0)
                if drawCount > 0:
                     self.log(f"联通祝福: [{activity['name']}] 可抽奖次数 {drawCount}")
                else:
                     self.log(f"联通祝福: [{activity['name']}] 今日已无抽奖机会")
                while drawCount > 0:
                    time.sleep(2)
                    self.wocare_luckDraw(activity, activeModuleGroupId)
                    drawCount -= 1
            else:
                msg = responseResult.get("resultMsg") or responseResult.get("resultDesc") or ""
                self.log(f"联通祝福: [{activity['name']}]查询活动失败[{resultCode}]: {msg}")
        except Exception as e:
            self.log(f"wocare_loadInit 异常: {str(e)}")

    def wocare_luckDraw(self, activity, activeModuleGroupId):
        try:
            apiCode = "luckDraw"
            requestData = {
                "token": self.wocare_token,
                "channelType": WOCARE_CONSTANTS["serviceLife"],
                "zActiveModuleGroupId": activeModuleGroupId,
                "type": activity["id"],
                "apiCode": apiCode
            }
            result = self.wocare_api(apiCode, requestData)
            responseResult = result if result else {}
            resultCode = responseResult.get("resultCode", "-1")
            if resultCode == "0000":
                resultData = responseResult.get("data", {}) or {}
                drawResultCode = resultData.get("resultCode", "-1")
                if drawResultCode == "0000":
                    prize = resultData.get("data", {}).get("prize", {})
                    prizeName = prize.get("prizeName", "")
                    prizeDesc = prize.get("prizeDesc", "")
                    self.log(f"联通祝福: [{activity['name']}]抽奖: {prizeName}[{prizeDesc}]", notify=True)
                else:
                    msg = responseResult.get("resultMsg") or responseResult.get("resultDesc") or ""
                    if msg.lower() == "success":
                        self.log(f"联通祝福: [{activity['name']}] 未中奖 (继续努力)")
                    else:
                        self.log(f"联通祝福: [{activity['name']}] 抽奖并未中奖: {msg}")
            else:
                msg = responseResult.get("resultMsg") or responseResult.get("resultDesc") or ""
                if msg.lower() == "success":
                    self.log(f"联通祝福: [{activity['name']}] 未中奖 (继续努力)")
                else:
                    self.log(f"联通祝福: [{activity['name']}] 抽奖异常[{resultCode}]: {msg}")
        except Exception as e:
            self.log(f"wocare_luckDraw 异常: {str(e)}")

    def parse_jwt_payload(self, token):
        try:
            payload = token.split('.')[1]
            padding = len(payload) % 4
            if padding:
                payload += '=' * (4 - padding)
            payload = payload.replace('-', '+').replace('_', '/')
            decoded_bytes = base64.b64decode(payload)
            return json.loads(decoded_bytes.decode('utf-8'))
        except Exception as e:
            self.log(f"JWT Decode Error: {e}")
            return {}

    def generate_market_signature_headers(self, user_token, query_string="", json_body=""):
        try:
            token = user_token.replace('Bearer ', '')
            payload = self.parse_jwt_payload(token)
            login_id = payload.get('loginId', '')
            app_secret = hashlib.md5(f"al:ak:{login_id}".encode('utf-8')).hexdigest()
            nonce = str(uuid.uuid4())
            message = f"{login_id}{app_secret}{nonce}{query_string or ''}{json_body or ''}"
            signature = base64.b64encode(
                hmac.new(
                    app_secret.encode('utf-8'),
                    message.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).digest()
            ).decode('utf-8')
            return {
                'X-User-Id': login_id,
                'X-Nonce': nonce,
                'X-Timestamp': str(int(time.time() * 1000)),
                'X-Signature': signature,
                'Content-Type': 'application/json'
            }
        except Exception as e:
            self.log(f"Signature Generation Error: {e}")
            return {}

    def get_market_headers(self, user_token):
        return {
            'User-Agent': COMMON_CONSTANTS['MARKET_UA'],
            'Authorization': f"Bearer {user_token}",
            'Content-Type': 'application/json',
            'X-Requested-With': 'com.sinovatech.unicom.ui'
        }

    def market_get_ticket(self):
        self.log("权益超市: 正在获取 ticket...")
        target_url = "https://contact.bol.wo.cn/market"
        res = self.openPlatLineNew(target_url)
        if res and 'ticket' in res:
            self.log("权益超市: 获取ticket成功")
            return res['ticket']
        self.log("权益超市: 获取ticket失败")
        return None

    def market_get_user_token(self, ticket):
        url = f"https://backward.bol.wo.cn/prod-api/auth/marketUnicomLogin?ticket={ticket}"
        headers = {
            'User-Agent': COMMON_CONSTANTS['MARKET_UA'],
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
        }
        for attempt in range(1, 4):
            try:
                self.log(f"权益超市: 正在获取 userToken...{f' (第{attempt}次重试)' if attempt > 1 else ''}")
                res = self.session.post(url, headers=headers, timeout=30).json()
                if res.get('code') == 200:
                    user_token = res.get('data', {}).get('token')
                    if user_token:
                        self.log("权益超市: 获取userToken成功")
                        return user_token
                self.log(f"权益超市: 获取userToken失败: {res.get('msg')}")
            except Exception as e:
                self.log(f"权益超市: 获取userToken异常: {e}")
            if attempt < 3:
                self.log(f"权益超市: 等待5秒后重试...")
                time.sleep(5)
        return None

    def query_market_watering_status(self, user_token):
        try:
            status_url = "https://backward.bol.wo.cn/prod-api/promotion/activityTask/getMultiCycleProcess?activityId=13"
            headers = self.get_market_headers(user_token)
            res = self.session.get(status_url, headers=headers).json()
            if res.get('code') == 200:
                data = res.get('data', {})
                triggered_time = data.get('triggeredTime', 0)
                trigger_time = data.get('triggerTime', 0)
                create_date = data.get('createDate', '')
                self.log(f"权益超市-浇花当前状况: 进度 {triggered_time}/{trigger_time}", notify=True)
                if triggered_time >= trigger_time:
                    self.log("权益超市-浇花: 🌟 您有鲜花权益待领取! (连续浇花已满) 🌟", notify=True)
                else:
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    last_watered = create_date.split(' ')[0] if create_date else ''
                    if today_str == last_watered:
                        self.log(f"权益超市-浇花: 今日已浇水 (最后: {create_date})", notify=True)
                    else:
                        self.log("权益超市-浇花: 今日尚未浇水。")
            else:
                self.log(f"权益超市-浇花查验: 查询状态失败: {res.get('msg')}")
        except Exception as e:
            self.log(f"权益超市-浇花查验: 异常: {e}")

    def market_watering_task(self, user_token):
        self.log("权益超市: 浇花任务开始...")
        try:
            status_url = "https://backward.bol.wo.cn/prod-api/promotion/activityTask/getMultiCycleProcess?activityId=13"
            headers = self.get_market_headers(user_token)
            res = self.session.get(status_url, headers=headers).json()
            if res.get('code') != 200:
                self.log(f"权益超市-浇花: 获取状态失败: {res.get('msg')}")
                return
            data = res.get('data', {})
            triggered_time = data.get('triggeredTime', 0)
            trigger_time = data.get('triggerTime', 0)
            create_date = data.get('createDate', '')
            self.log(f"权益超市-浇花: 当前进度 {triggered_time}/{trigger_time}", notify=True)
            if triggered_time >= trigger_time:
                self.log("权益超市-浇花: 🌟 您有鲜花权益待领取! (连续浇花已满) 🌟", notify=True)
                return
            today_str = datetime.now().strftime('%Y-%m-%d')
            last_watered = create_date.split(' ')[0] if create_date else ''
            if today_str == last_watered:
                self.log(f"权益超市-浇花: 今日已浇水 (最后: {create_date})", notify=True)
                return
            self.log("权益超市-浇花: 今日未浇水，执行浇水操作...")
            timestamp = int(time.time() * 1000)
            query_string = f"xbsosjl=xbsosjlsujif&timeVerRan={timestamp}"
            json_body = "{}"
            sig_headers = self.generate_market_signature_headers(user_token, query_string, json_body)
            watering_url = f"https://backward.bol.wo.cn/prod-api/promotion/activityTaskShare/checkWatering?{query_string}"
            req_headers = headers.copy()
            req_headers.update(sig_headers)
            req_headers['Referer'] = 'https://contact.bol.wo.cn/market'
            req_headers['Origin'] = 'https://contact.bol.wo.cn'
            res = self.session.post(watering_url, headers=req_headers, data=json_body).json()
            if res.get('code') == 200:
                self.log("权益超市-浇花: ✅ 浇水成功!", notify=True)
            else:
                self.log(f"权益超市-浇花: ❌ 浇水失败: {res.get('msg')}")
        except Exception as e:
            self.log(f"权益超市-浇花: 异常: {e}")

    def market_get_raffle(self, user_token):
        self.log("权益超市: 正在查询奖品池...")
        try:
            timestamp = int(time.time() * 1000)
            query_string = f"id=12&timeVerRan={timestamp}"
            json_body = "{}"
            sig_headers = self.generate_market_signature_headers(user_token, query_string, json_body)
            url = f"https://backward.bol.wo.cn/prod-api/promotion/home/raffleActivity/prizeList?{query_string}"
            headers = self.get_market_headers(user_token)
            headers.update(sig_headers)
            headers['Referer'] = 'https://contact.bol.wo.cn/market'
            headers['Origin'] = 'https://contact.bol.wo.cn'
            res = self.session.post(url, headers=headers, data=json_body).json()
            if res.get('code') == 200 and isinstance(res.get('data'), list):
                keywords = ['月卡', '月会员', '月度', 'VIP月', '一个月', '周卡']
                exclude = ['5G宽视界', '沃视频']
                live_prizes = []
                for p in res['data']:
                    vip_prob = float(p.get('probabilityVip') or p.get('newVipProbability') or 0)
                    norm_prob = float(p.get('probability') or 0)
                    name = p.get('name', '')
                    daily_limit = int(p.get('dailyPrizeLimit') or 0)
                    match = any(k in name for k in keywords)
                    not_excluded = not any(e in name for e in exclude)
                    has_stock = daily_limit > 0
                    has_chance = norm_prob > 0 or vip_prob > 0
                    if match and not_excluded and has_stock and has_chance:
                        live_prizes.append(p)
                        total_limit = int(p.get('quantity') or 0)
                        self.log(f"权益超市: 【{name}】监测到放水 (日库存:{daily_limit}, 总库存:{total_limit}, 普通概率:{(norm_prob * 100):.4f}%, VIP概率:{(vip_prob * 100):.4f}%)")
                if live_prizes:
                    return True
            self.log("权益超市: 📢 未监测到高价值权益放水")
            return False
        except Exception as e:
            self.log(f"权益超市: 查询奖品池异常: {e}")
            return False

    def market_get_raffle_count(self, user_token):
        try:
            timestamp = int(time.time() * 1000)
            query_string = f"id=12&channel=unicomTab&timeVerRan={timestamp}"
            json_body = "{}"
            sig_headers = self.generate_market_signature_headers(user_token, query_string, json_body)
            url = f"https://backward.bol.wo.cn/prod-api/promotion/home/raffleActivity/getUserRaffleCountExt?{query_string}"
            headers = self.get_market_headers(user_token)
            headers.update(sig_headers)
            headers['Referer'] = 'https://contact.bol.wo.cn/market'
            headers['Origin'] = 'https://contact.bol.wo.cn'
            res = self.session.post(url, headers=headers, data=json_body).json()
            count = 0
            if res.get('code') == 200:
                data = res.get('data')
                if isinstance(data, dict):
                    count = int(data.get('raffleCount') or 0)
                else:
                    count = int(data or 0)
            if count > 0:
                self.log(f"权益超市: ✅ 当前抽奖次数: {count}")
                for i in range(count):
                    self.log(f"权益超市: 🎯 第 {i+1} 次抽奖...")
                    if not self.market_user_raffle(user_token):
                        break
                    time.sleep(3 + random.random() * 2)
            else:
                self.log("权益超市: 当前无抽奖次数")
        except Exception as e:
            self.log(f"权益超市: 查询抽奖次数异常: {e}")

    def market_user_raffle(self, user_token):
        try:
            timestamp = int(time.time() * 1000)
            query_string = f"id=12&channel=unicomTab&timeVerRan={timestamp}"
            json_body = "{}"
            sig_headers = self.generate_market_signature_headers(user_token, query_string, json_body)
            url = f"https://backward.bol.wo.cn/prod-api/promotion/home/raffleActivity/userRaffle?{query_string}"
            headers = self.get_market_headers(user_token)
            headers.update(sig_headers)
            headers['Referer'] = 'https://contact.bol.wo.cn/market'
            res = self.session.post(url, headers=headers, data=json_body).json()
            if res.get('code') == 200:
                data = res.get('data', {})
                prize_name = data.get('prizesName', '')
                message = data.get('message') or res.get('msg') or ""
                if prize_name and "谢谢参与" not in prize_name:
                    self.log(f"权益超市: 🎉 抽奖成功: {prize_name}", notify=True)
                    return True
                self.log(f"权益超市: 💨 未中奖: {message}", notify=True)
                return True
            self.log(f"权益超市: 抽奖失败: {res.get('msg')}")
            return False
        except Exception as e:
            self.log(f"权益超市: 抽奖异常: {e}")
            return False

    def market_get_all_tasks(self, ecs_token, user_token):
        url = "https://backward.bol.wo.cn/prod-api/promotion/activityTask/getAllActivityTasks?activityId=12"
        headers = {
            "Authorization": f"Bearer {user_token}",
            "User-Agent": COMMON_CONSTANTS["MARKET_UA"],
            "Origin": "https://contact.bol.wo.cn",
            "Referer": "https://contact.bol.wo.cn/",
            "Cookie": f"ecs_token={ecs_token}"
        }
        for attempt in range(1, 4):
            try:
                self.log(f"权益超市: 正在获取任务列表...{f' (第{attempt}次重试)' if attempt > 1 else ''}")
                res = self.session.get(url, headers=headers, timeout=15).json()
                if res.get('code') == 200:
                    tasks = res.get('data', {}).get('activityTaskUserDetailVOList', [])
                    self.log(f"权益超市: 成功获取到 {len(tasks)} 个任务")
                    return tasks
                self.log(f"权益超市: 查询任务列表失败: {res.get('msg')}")
            except Exception as e:
                self.log(f"权益超市: 获取任务列表异常: {e}")
            if attempt < 3:
                self.log("权益超市: 等待5秒后重试...")
                time.sleep(5)
        return []

    def market_do_share_list(self, share_list, user_token):
        self.log("权益超市: 开始执行任务...")
        for task in share_list:
            name = task.get('name', '')
            param = task.get('param1', '')
            trigger_time = task.get('triggerTime', 0)
            triggered_time = task.get('triggeredTime', 0)
            if any(k in name for k in ["购买", "秒杀"]):
                 self.log(f"权益超市: 🚫 {name} [跳过]")
                 continue
            if triggered_time >= trigger_time:
                 self.log(f"权益超市: ✅ {name} [已完成]")
                 continue
            url = ""
            if any(k in name for k in ["浏览", "查看"]):
                url = f"https://backward.bol.wo.cn/prod-api/promotion/activityTaskShare/checkView?checkKey={param}"
            elif "分享" in name:
                url = f"https://backward.bol.wo.cn/prod-api/promotion/activityTaskShare/checkShare?checkKey={param}"
            if url:
                try:
                    headers = {
                        "Authorization": f"Bearer {user_token}",
                        "User-Agent": COMMON_CONSTANTS["MARKET_UA"],
                        "Origin": "https://contact.bol.wo.cn",
                        "Referer": "https://contact.bol.wo.cn/"
                    }
                    res = self.session.post(url, json={}, headers=headers, timeout=15).json()
                    if res.get('code') == 200:
                        self.log(f"权益超市: ✅ {name} [执行成功]")
                    else:
                        self.log(f"权益超市: ❌ {name} [执行失败]: {res.get('msg')}")
                except Exception as e:
                    self.log(f"权益超市: ❌ {name} [执行异常]: {e}")
            time.sleep(2)

    def market_task(self, is_query_only=False):
        self.log("==== 权益超市 ====")
        ticket = self.market_get_ticket()
        if not ticket:
            return
        user_token = self.market_get_user_token(ticket)
        if not user_token:
            return
        if is_query_only:
            self.query_market_watering_status(user_token)
            self.query_market_raffle_records(user_token)
            self.query_phone_recharge_records(user_token)
            return
        mc = globalConfig.get("market_config", {})
        if mc.get("run_water", True):
            self.market_watering_task(user_token)
            time.sleep(2)
        else:
            self.log("权益超市-浇水: ⏭️ 已被总开关关闭，跳过")
        if mc.get("run_task", True):
            if hasattr(self, 'ecs_token'):
                share_list = self.market_get_all_tasks(self.ecs_token, user_token)
                if share_list:
                    self.market_do_share_list(share_list, user_token)
            else:
                 self.log("权益超市: 缺 ecs_token, 跳过任务列表")
        else:
            self.log("权益超市-做任务: ⏭️ 已被总开关关闭，跳过")
        if mc.get("run_draw", True):
            if self.market_get_raffle(user_token):
                self.market_get_raffle_count(user_token)
        else:
            self.log("权益超市-抽奖: ⏭️ 已被总开关关闭，跳过")
        if mc.get("run_claim", False):
            self.log("权益超市-领奖: 自动领奖已开启")
            self.query_phone_recharge_records(user_token)
        else:
            self.log("权益超市-领奖: ⏭️ 未开启自动领奖")
        self.query_market_raffle_records(user_token)
        self.query_phone_recharge_records(user_token)

    def init_cloud_urls(self):
        if not hasattr(self, 'cloudDiskUrls'):
            self.cloudDiskUrls = {
                'onLine': "https://m.client.10010.com/mobileService/onLine.htm",
                'getTicketByNative': "https://m.client.10010.com/edop_ng/getTicketByNative",
                'userticket': "https://panservice.mail.wo.cn/api-user/api/user/ticket",
                'ltypDispatcher': "https://panservice.mail.wo.cn/wohome/dispatcher",
                'query': "https://m.jf.10010.com/jf-external-application/page/query",
                'taskDetail': "https://m.jf.10010.com/jf-external-application/jftask/taskDetail",
                'dosign': "https://m.jf.10010.com/jf-external-application/jftask/sign",
                'doUpload': "https://b.smartont.net/openapi/transfer/quickTransfer",
                'doPopUp': "https://m.jf.10010.com/jf-external-application/jftask/popUp",
                'toFinish': "https://m.jf.10010.com/jf-external-application/jftask/toFinish",
                'lottery': "https://panservice.mail.wo.cn/activity/lottery",
                'activityList': "https://panservice.mail.wo.cn/activity/v1/activityList",
                'userInfo': "https://m.jf.10010.com/jf-external-application/jftask/userInfo",
                'ai_query': "https://panservice.mail.wo.cn/wohome/ai/assistant/query",
                'lottery_times': "https://panservice.mail.wo.cn/activity/lottery/lottery-times",
                'aiMoveFile': "https://panservice.mail.wo.cn/wohome/open/v1/ai/moveFile2SystemFolder",
            }

    def cloudRequest(self, url_name, payload, is_changer=False, method='post', custom_headers=None):
        self.init_cloud_urls()
        url = self.cloudDiskUrls.get(url_name)
        if not url:
            self.log(f"云盘无效的URL名称: {url_name}")
            return {'result': None, 'headers': None}
        headers = {
            'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301}",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
        }
        if custom_headers:
             headers.update(custom_headers)
        if url_name in ['dosign', 'userInfo', 'doPopUp', 'toFinish', 'taskDetail']:
            if not getattr(self.cloudDisk, 'userticket', None):
                self.log(f"云盘 [{{url_name}}] userticket 未获取")
                return {'result': None, 'headers': None}
            headers['ticket'] = self.cloudDisk.userticket
            headers['content-type'] = "application/json;charset=UTF-8"
            headers['partnersid'] = "1649"
            headers['origin'] = "https://m.jf.10010.com"
            if getattr(self.cloudDisk, 'jeaId', None):
                headers['Cookie'] = f"_jea_id={self.cloudDisk.jeaId}"
            if is_changer:
                headers['clienttype'] = "yunpan_unicom_applet"
                headers['x-requested-with'] = "com.sinovatech.unicom.ui"
                if url_name == 'toFinish':
                    headers['User-Agent'] = "Mozilla/5.0 (Linux; Android 12; Redmi K30 Pro Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.39 Mobile Safari/537.36/woapp LianTongYunPan/4.0.4 (Android 12)"
                    headers['clienttype'] = "yunpan_android"
                    headers['x-requested-with'] = "com.chinaunicom.bol.cloudapp"
            else:
                headers['clienttype'] = "yunpan_android"
                headers['x-requested-with'] = "com.sinovatech.unicom.ui"
        elif url_name == 'activityList':
            headers.update({
                'User-Agent': "Mozilla/5.0 (Linux; Android 12; Redmi K30 Pro Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.39 Mobile Safari/537.36/woapp LianTongYunPan/4.0.4 (Android 12)",
                'Accept': "application/json, text/plain, */*",
                'Content-Type': "application/json",
                'Client-Id': "1001000035",
                'App-Version': "yp-app/4.0.4",
                'Access-Token': self.cloudDisk.userToken,
                'Sys-Version': "android/12",
                'Origin': "https://panservice.mail.wo.cn",
                'X-Requested-With': "com.chinaunicom.bol.cloudapp",
                'Referer': "https://panservice.mail.wo.cn/h5/mobile/wocloud/activityCenter/home"
            })
        elif url_name == 'doUpload':
            headers.update({
                'User-Agent': "okhttp-okgo/jeasonlzy LianTongYunPan/5.1.0 (Android 15)",
                'client-Id': "1001000035",
                'app-version': "yp-app/5.1.0",
                'access-token': self.cloudDisk.userToken,
                'Content-Type': "application/json;charset=utf-8",
                'X-YP-Device-Id': 'yOH1Y2/Ck5tBHRRBEAPCoGRGBOHCob7I',
                'Host': 'b.smartont.net'
            })
        elif url_name == 'ai_query':
             model_id = payload.get('modelId', 1)
             headers.update({
                'accept': 'text/event-stream',
                'X-YP-Access-Token': self.cloudDisk.userToken,
                'X-YP-App-Version': '5.0.12',
                'X-YP-Client-Id': '1001000035',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 9; SM-N9810 Build/PQ3A.190705.11211540; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Mobile Safari/537.36/woapp LianTongYunPan/5.0.12 (Android 9)',
                'Content-Type': 'application/json',
                'Origin': 'https://panservice.mail.wo.cn',
                'X-Requested-With': 'com.chinaunicom.bol.cloudapp',
                'Referer': f"https://panservice.mail.wo.cn/h5/wocloud_ai/?modelType={model_id}&clientId=1001000035&touchpoint=300300010001&token={self.cloudDisk.userToken}",
             })
        elif url_name == 'lottery_times':
             method = 'get'
             headers.update({
                 'X-YP-Access-Token': self.cloudDisk.userToken, 'source-type': 'woapi', 'clientId': '1001000165',
                 'token': self.cloudDisk.userToken, 'X-YP-Client-Id': '1001000165',
             })
        elif url_name == 'aiMoveFile':
             headers.update({
                 'X-YP-Device-Id': 'yOH1Y2/Ck5tBHRRBEAPCoGRGBOHCob7I',
                 'app-type': 'liantongyunpanapp',
                 'Access-Token': self.cloudDisk.userToken,
                 'Client-Id': '1001000035',
                 'App-Version': 'yp-app/5.1.0',
                 'Sys-Version': 'Android/15',
                 'User-Agent': 'LianTongYunPan/5.1.0 (Android 15)',
                 'X-YP-Client-Id': '1001000035',
                 'X-YP-Access-Token': self.cloudDisk.userToken,
                 'oaid': '00000000',
                 'Content-Type': 'application/json;charset=utf-8',
                 'Origin': 'https://panservice.mail.wo.cn',
             })
        elif url_name.startswith('cloud_') or 'shareCard' in url_name:
             current_token = getattr(self.cloudDisk, 'userToken', '')
             headers.update({
                'Host': 'panservice.mail.wo.cn',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 15; PJZ110 Build/AP3A.240617.008; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.109 Mobile Safari/537.36/woapp LianTongYunPan/5.1.0 (Android 15)',
                'client-Id': '1001000035',
                'X-YP-Client-Id': '1001000035',
                'accessToken': current_token,
                'access-token': current_token,
                'X-YP-Access-Token': current_token,
                'Authorization': f'Bearer {current_token}',
                'X-Requested-With': 'com.chinaunicom.bol.cloudapp',
                'Content-Type': 'application/json',
                'Origin': 'https://panservice.mail.wo.cn',
             })
             touchpoint = '300300010032'
             if 'lightPuzzle' in url_name: touchpoint = '300300010003'
             if 'shareCardReceive' in url_name:
                  headers['User-Agent'] = "Mozilla/5.0 (Linux; Android 15; PJZ110 Build/AP3A.240617.008; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 Mobile Safari/537.36 XWEB/1420229 MMWEBSDK/20250802 MMWEBID/7928 MicroMessenger/8.0.62.2900(0x28003EA0) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64"
                  headers['X-Requested-With'] = "com.tencent.mm"
                  headers['X-YP-GRAY-FLAG'] = "undefined"
                  uniq_key = payload.get('uniqKey', '') if isinstance(payload, dict) else ''
                  card_code = payload.get('_cardCode', 'LT') if isinstance(payload, dict) else 'LT'
                  if isinstance(payload, dict) and '_cardCode' in payload:
                       del payload['_cardCode']
                  headers['Referer'] = f"https://panservice.mail.wo.cn/h5/activitymobile/newYears26?uniqKey={uniq_key}&cardCode={card_code}&activityId=SPRING_FESTIVAL_2026&page=1&touchpoint=undefined"
             else:
                  headers['Referer'] = f"https://panservice.mail.wo.cn/h5/activitymobile/newYears26?activityId=SPRING_FESTIVAL_2026&touchpoint={touchpoint}&token={current_token}"
                  if url_name == 'shareCard':
                       headers['X-YP-GRAY-FLAG'] = "undefined"
        for attempt in range(1, 4):
            try:
                if method == 'get':
                    res = self.session.get(url, params=payload, headers=headers, timeout=15)
                else:
                    res = self.session.post(url, json=payload, headers=headers, timeout=15)
                if url_name == 'ai_query':
                     return {'result': None, 'body': res.text, 'headers': res.headers}
                try:
                    res_json = res.json()
                    return {'result': res_json, 'headers': res.headers, 'status': res.status_code}
                except:
                    return {'result': res.text, 'headers': res.headers, 'status': res.status_code}
            except Exception as e:
                err_msg = str(e)
                if attempt < 3 and os.environ.get("UNICOM_PROXY_API") and ("Max retries exceeded" in err_msg or "timed out" in err_msg.lower() or "connection" in err_msg.lower() or "SOCKS" in err_msg):
                    self.log(f"cloudRequest [{url_name}] 网络异常触发故障转移({err_msg}), 正在更换代理...")
                    self.failover_proxy()
                    continue
                if attempt == 3:
                     self.log(f"cloudRequest Exception [{url_name}]: {e}")
                     return {'result': None, 'headers': None, 'status': 599}
                self.log(f"cloudRequest [{url_name}] 网络异常({e}), 重试第{attempt}次...")
                time.sleep(2)

    def encrypt_data_cloud(self, data, key, iv="wNSOYIB1k1DjY5lA"):
        pass

    def getTicketByNative_cloud(self):
        for attempt in range(1, 4):
            try:
                url = f"{self.cloudDiskUrls['getTicketByNative']}?appId=edop_unicom_d67b3e30&token={self.ecs_token}"
                headers = {
                    'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301}",
                    'Connection': "Keep-Alive",
                    'Accept-Encoding': "gzip",
                }
                res = self.session.get(url, headers=headers).json()
                if res.get('ticket'):
                    self.cloudDisk.ticket = res['ticket']
                    return res['ticket']
                elif str(res.get('code')) == "9999":
                    self.log(f"getTicketByNative_cloud 票据失效或被拦截: {res}")
            except Exception as e:
                err_msg = str(e)
                if attempt < 3 and os.environ.get("UNICOM_PROXY_API") and ("Max retries exceeded" in err_msg or "timed out" in err_msg.lower() or "connection" in err_msg.lower() or "SOCKS" in err_msg):
                    self.log(f"getTicketByNative_cloud 第{attempt}次异常触发故障转移: {err_msg}")
                    self.failover_proxy()
                    continue
                self.log(f"getTicketByNative_cloud 第{attempt}次重试 - 异常: {e}")
                time.sleep(2)
        return None

    def get_ltypDispatcher_cloud(self, ticket):
        for attempt in range(1, 4):
            try:
                timestamp = str(int(time.time() * 1000))
                result_rnd = str(random.randint(123456, 199999))
                string_to_hash = "HandheldHallAutoLoginV2" + timestamp + result_rnd + "wohome"
                sign = hashlib.md5(string_to_hash.encode()).hexdigest()
                payload = {
                    "header": {
                        "key": "HandheldHallAutoLoginV2",
                        "resTime": timestamp,
                        "reqSeq": result_rnd,
                        "channel": "wohome",
                        "version": "",
                        "sign": sign
                    },
                    "body": {
                        "clientId": "1001000003",
                        "ticket": ticket
                    }
                }
                url = self.cloudDiskUrls['ltypDispatcher']
                headers = {'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 12; leijun Pro Build/SKQ1.22013.001);unicom{version:android@11.0702}"}
                res = self.session.post(url, json=payload, headers=headers).json()
                token = res.get('RSP', {}).get('DATA', {}).get('token')
                if token:
                    self.cloudDisk.userToken = token
                    return token
            except Exception as e:
                 err_msg = str(e)
                 if attempt < 3 and os.environ.get("UNICOM_PROXY_API") and ("Max retries exceeded" in err_msg or "timed out" in err_msg.lower() or "connection" in err_msg.lower() or "SOCKS" in err_msg):
                     self.log(f"get_ltypDispatcher_cloud 第{attempt}次异常触发故障转移: {err_msg}")
                     self.failover_proxy()
                     continue
                 self.log(f"get_ltypDispatcher_cloud 第{attempt}次重试 - 异常: {e}")
                 time.sleep(2)
        return None

    def get_userticket_cloud(self, is_changer=False):
        if not getattr(self.cloudDisk, 'userToken', None):
            self.log("云盘任务: 获取userticket失败, userToken未获取")
            return None
        headers = {}
        if is_changer:
            headers = {
                'User-Agent': "LianTongYunPan/4.0.4 (Android 12)",
                'app-type': "liantongyunpanapp",
                'Client-Id': "1001000035",
                'App-Version': "yp-app/4.0.4",
                'Sys-Version': "Android/12",
                'X-YP-Client-Id': "1001000035",
                'X-YP-Access-Token': self.cloudDisk.userToken,
            }
        else:
             headers = {
                'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301}",
                'Content-Type': 'application/json',
                'X-YP-Access-Token': self.cloudDisk.userToken,
                'accesstoken': self.cloudDisk.userToken,
                'token': self.cloudDisk.userToken,
                'clientId': "1001000003",
                'X-YP-Client-Id': "1001000003",
                'source-type': "woapi",
                'app-type': "unicom"
             }
        for attempt in range(1, 4):
            try:
                 res = self.session.post(self.cloudDiskUrls['userticket'], json={}, headers=headers, timeout=15).json()
                 if res and isinstance(res, dict) and res.get('result', {}).get('ticket'):
                     self.cloudDisk.userticket = res['result']['ticket']
                     return self.cloudDisk.userticket
                 else:
                     self.log(f"get_userticket_cloud failed: {res}")
                     return None
            except Exception as e:
                 self.log(f"[get_userticket_cloud] 请求异常[{e}]，重试第{attempt}次")
                 time.sleep(2)
        return None

    def get_userInfo_cloud(self):
        if not self.get_userticket_cloud(False): return
        data = self.cloudRequest('userInfo', {}, False, 'post')
        res = data.get('result')
        headers = data.get('headers')
        if headers:
            cookie = headers.get('Set-Cookie', '')
            match = re.search(r'_jea_id=([^;]+)', cookie)
            if match:
                self.cloudDisk.jeaId = match.group(1)
        if res and res.get('data'):
             avail = res['data'].get('availableScore')
             today_earn = res['data'].get('todayEarnScore', 0)
             if not hasattr(self.cloudDisk, 'initial_avail'):
                 self.cloudDisk.initial_avail = avail
                 self.log(f"云盘任务: 运行前 - 今日已赚: {today_earn}, 可用积分: {avail}")
             else:
                 earned = int(avail) - int(self.cloudDisk.initial_avail)
                 self.log(f"云盘任务: 运行后 - 今日已赚: {today_earn}, 可用: {avail}, 本次获得: {earned}", notify=True)

    def do_ai_interaction_cloud(self, taskCode, taskName):
        self.log(f"云盘任务: 执行AI通通查询请求...")
        payload = {
          "input": "你好",
          "platform": 2,
          "modelId": 0,
          "tag": 21,
          "subTag": 210000,
          "conversationId": "",
          "knowledgeId": "",
          "referFileInfo": []
        }
        data = self.cloudRequest('ai_query', payload, False, 'post')
        body = data.get('body', '')
        if body and ('"finish":1' in body or 'success' in body):
             self.log(f"云盘任务: ✅ [{taskName}] 互动成功")
             return True
        self.log(f"云盘任务: ❌ [{taskName}] 互动失败")
        return False

    def doUpload_cloud(self, taskCode, taskName, prefix="云盘任务"):
        if not self.get_userticket_cloud(False): return False
        timestamp = int(time.time() * 1000)
        fileName = f"{timestamp}.jpeg"
        batchNo = hashlib.md5(f"{timestamp}{random.random()}".encode()).hexdigest().upper()
        payload = {
          "batchNo": batchNo, "deviceId": "", "directoryId": "0", "familyId": 0,
          "fileModificationTime": timestamp, "fileName": fileName, "fileSize": "1154452",
          "fileType": "1", "height": "1919", "lat": "", "lng": "", "psToken": "",
          "sha256": "792c4ea2285563c6c445b92cd3df14fd71360d21559139cebd95484a98bc013f",
          "spaceType": "0", "width": "1080"
        }
        data = self.cloudRequest('doUpload', payload, False, 'post')
        res = data.get('result')
        if not isinstance(res, dict):
             res = {}
        code = res.get('meta', {}).get('code')
        code2 = res.get('code')
        if code == "0000" or code2 == 200 or str(code2) == "200":
             self.log(f"{prefix}: [{taskName}] 上传成功")
             if not taskCode: return True  # 春节活动上传无需领奖
             time.sleep(1)
             self.doPopUp_cloud(taskCode, taskName, False)
             return True
        self.log(f"{prefix}: ❌ [{taskName}] 上传失败: {res}")
        return False

    def doPopUp_cloud(self, taskCode, taskName, is_changer):
        if not self.get_userticket_cloud(is_changer): return
        time.sleep(5)
        data = self.cloudRequest('doPopUp', {}, is_changer, 'post')
        res = data.get('result')
        if not isinstance(res, dict):
             res = {}
        code = res.get('meta', {}).get('code')
        code2 = res.get('code')
        if str(code) == "0000" or str(code) == "0" or str(code2) == "0000" or str(code2) == "0":
             score = res.get('data', {}).get('score', 0)
             self.log(f"云盘任务: ✅ [{taskName}] 完成, 获得积分: {score}", notify=True)
        else:
             self.log(f"云盘任务: ❌ [{taskName}] 领取奖励失败: {res}")

    def toFinish_cloud(self, taskCode, taskName, is_changer):
        if not self.get_userticket_cloud(is_changer): return False
        data = self.cloudRequest('toFinish', {'taskCode': taskCode}, is_changer, 'post')
        res = data.get('result')
        if not isinstance(res, dict):
             res = {}
        if res.get('code') == "0000": return True
        return False

    def dosign_cloud(self, taskCode, taskName):
        if not self.get_userticket_cloud(False): return
        data = self.cloudRequest('dosign', {'taskCode': taskCode}, False, 'post')
        res = data.get('result')
        if not isinstance(res, dict):
             res = {}
        if "0000" in str(res.get('code')) and res.get('data', {}).get('score'):
             self.log(f"云盘任务: ✅ [{taskName}] 完成, 获得积分: {res['data']['score']}", notify=True)
        else:
             self.log(f"云盘任务: ❌ [{taskName}] 失败: {res}")

    def activityList_cloud(self, taskCode, taskName):
        if not self.get_userticket_cloud(True): return
        payload = { "bizKey": "activityCenterPipeline", "bizObject": { "pageNo": 1 } }
        data = self.cloudRequest('activityList', payload, True, 'post')
        res = data.get('result')
        if not isinstance(res, dict):
             res = {}
        if str(res.get('meta', {}).get('code')) == "0":
             time.sleep(2)
             self.doPopUp_cloud(taskCode, taskName, True)
        else:
             self.log(f"云盘任务: ❌ [{taskName}] 浏览活动失败: {res}")

    def get_taskDetail_cloud(self):
        if not self.get_userticket_cloud(False): return
        data = self.cloudRequest('taskDetail', {}, False, 'post')
        res = data.get('result')
        if not isinstance(res, dict):
             res = {}
        taskList = res.get('data', {}).get('taskDetail', {}).get('taskList', [])
        taskNameList = ["浏览活动中心", "分享文件", "签到", "与AI通通互动", "打开相册自动备份"]
        for task in taskList:
            time.sleep(0.5)
            tName = task.get('taskName', '')
            tCode = task.get('taskCode')
            finishText = task.get('finishText')
            is_finished = finishText in ["已完成", "已领取"] or task.get('finishState', False) == True or (finishText and "/" in str(finishText) and "0/" not in str(finishText))
            if is_finished and any(target in tName for target in taskNameList):
                self.log(f"云盘任务: ✅ [{tName}] 已完成")
                continue
            if finishText == "未完成" or finishText == "去完成" or "0/" in str(finishText) or (not task.get('finishState', True)):
                matched = False
                for target in taskNameList:
                    if target in tName: matched = True
                if matched:
                    self.log(f"云盘任务: 开始执行 [{tName}]")
                    if "浏览活动中心" in tName:
                        self.toFinish_cloud(tCode, tName, True)
                        self.activityList_cloud(tCode, tName)
                    elif "分享文件" in tName:
                        self.log("云盘任务: 分享文件任务暂跳过(需加密实现)")
                    elif "签到" in tName:
                        self.toFinish_cloud(tCode, tName, False)
                        self.dosign_cloud(tCode, tName)
                    elif "与AI通通互动" in tName:
                        self.toFinish_cloud(tCode, tName, False)
                        self.do_ai_interaction_cloud(tCode, tName)
                    elif "打开相册自动备份" in tName:
                        self.toFinish_cloud(tCode, tName, False)
                        if self.get_userticket_cloud(True):
                             payload = { "bizKey": "activityCenterPipeline", "bizObject": { "pageNo": 1 } }
                             d = self.cloudRequest('activityList', payload, True)
                             if str(d.get('result', {}).get('meta', {}).get('code')) == "0":
                                 self.log(f"云盘任务: ✅ [{tName}] 打开成功")
                                 time.sleep(2)
            if finishText == "未完成" and "手动上传文件" in tName:
                subtitle = task.get('taskNameSubtitle', '')
                try:
                    nums = re.findall(r'\d+', subtitle)
                    if len(nums) >= 2:
                        curr = int(nums[0])
                        target = int(nums[1])
                        if curr < target:
                            needed = target - curr
                            self.log(f"云盘任务: [{tName}] 需 {needed} 次")
                            self.toFinish_cloud(tCode, tName, False)
                            for i in range(needed):
                                if self.doUpload_cloud(tCode, tName):
                                    self.log(f"云盘任务: [{tName}] 第 {curr + i + 1} 次上传完成")
                                    time.sleep(0.5)
                                else:
                                    break
                except: pass

    def ltyp_task(self, is_query_only=False):
        self.log("==== 联通云盘任务 ====")
        self.init_cloud_urls()

        class CloudDiskState: pass
        self.cloudDisk = CloudDiskState()
        if not self.ecs_token:
            self.log("云盘任务: 缺少 ecs_token，跳过。")
            return
        ticket = self.getTicketByNative_cloud()
        if not ticket: return
        if not hasattr(self, 'city_info') or not self.city_info:
             self.get_city_info()
        token = self.get_ltypDispatcher_cloud(ticket)
        if not token: return
        time.sleep(0.5)
        self.get_userInfo_cloud()
        if is_query_only:
            self.log("云盘任务: [查询模式] 跳过任务执行...")
            self.get_userInfo_cloud()
            return
        time.sleep(0.5)
        self.get_taskDetail_cloud()
        time.sleep(0.5)
        self.get_userInfo_cloud()

    def getTicketByNative_sec(self):
        for attempt in range(1, 4):
            try:
                url = f"https://m.client.10010.com/edop_ng/getTicketByNative?token={self.ecs_token}&appId=edop_unicom_3a6cc75a"
                city_code = ""
                cookie_str = f"PvSessionId={datetime.now().strftime('%Y%m%d%H%M%S')}{self.unicomTokenId};c_mobile={self.account_mobile}; c_version=iphone_c@11.0800; city=036|{city_code}|90063345|-99;devicedId={self.unicomTokenId}; ecs_token={self.ecs_token};t3_token="
                headers = {
                    "Cookie": cookie_str,
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "ChinaUnicom4.x/12.3.1 (com.chinaunicom.mobilebusiness; build:77; iOS 16.6.0) Alamofire/4.7.3 unicom{version:iphone_c@12.0301}",
                    "Accept-Language": "zh-Hans-CN;q=1.0"
                }
                res = self.session.get(url, headers=headers, timeout=10)
                if res.status_code != 200:
                    self.log(f"安全管家: getTicketByNative_sec http请求失败 {res.status_code}")
                    return
                try:
                    result = res.json()
                except:
                    self.log(f"安全管家: getTicketByNative_sec json解析失败: {res.text[:100]}")
                    return
                self.sec_ticket1 = result.get('ticket')
                if self.sec_ticket1:
                    return
                else:
                    self.log(f"安全管家: getTicketByNative_sec 失败 - {result}")
            except Exception as e:
                err_msg = str(e)
                if attempt < 3 and os.environ.get("UNICOM_PROXY_API") and ("Max retries exceeded" in err_msg or "timed out" in err_msg.lower() or "connection" in err_msg.lower() or "SOCKS" in err_msg):
                    self.log(f"安全管家: getTicketByNative_sec 第{attempt}次异常触发故障转移: {err_msg}")
                    self.failover_proxy()
                    continue
                self.log(f"安全管家: getTicketByNative_sec 第{attempt}次重试 - 异常: {e}")
                time.sleep(2)

    def getAuthToken_sec(self):
        if not getattr(self, 'sec_ticket1', None):
            self.log("安全管家 getAuthToken_sec 缺少 ticket1，跳过")
            return
        try:
            url = "https://uca.wo116114.com/api/v1/auth/ticket?product_line=uasp&entry_point=h5&entry_point_id=edop_unicom_3a6cc75a"
            headers = {
                "User-Agent": "ChinaUnicom4.x/12.3.1 (com.chinaunicom.mobilebusiness; build:77; iOS 16.6.0) Alamofire/4.7.3 unicom{version:iphone_c@12.0301}",
                "Content-Type": "application/json",
                "clientType": "uasp_unicom_applet"
            }
            data = { "productId": "", "type": 1, "ticket": self.sec_ticket1 }
            res = self.session.post(url, json=data, headers=headers).json()
            if res.get('data'):
                self.sec_token = res['data'].get('access_token')
            else:
                self.log(f"安全管家: getAuthToken_sec 失败 - {res}")
        except Exception as e:
            self.log(f"安全管家: getAuthToken_sec 异常: {e}")

    def getTicketForJF_sec(self):
        if not getattr(self, 'sec_token', None):
            self.log("安全管家 getTicketForJF_sec 缺少 token，跳过")
            return
        try:
            url1 = "https://uca.wo116114.com/api/v1/auth/getTicket?product_line=uasp&entry_point=h5&entry_point_id=edop_unicom_3a6cc75a"
            headers1 = {
                "User-Agent": "ChinaUnicom4.x/12.3.1 (com.chinaunicom.mobilebusiness; build:77; iOS 16.6.0) Alamofire/4.7.3 unicom{version:iphone_c@12.0301}",
                "Content-Type": "application/json",
                "auth-sa-token": self.sec_token,
                "clientType": "uasp_unicom_applet"
            }
            data1 = { "productId": "91311616", "phone": self.account_mobile }
            res1 = self.session.post(url1, json=data1, headers=headers1).json()
            if res1.get('data'):
                self.sec_ticket = res1['data'].get('ticket')
            else:
                self.log("安全管家获取积分票据失败")
                return
            url2 = "https://m.jf.10010.com/jf-external-application/page/query"
            headers2 = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301};ltst;OSVersion/16.6",
                "partnersid": "1702",
                "ticket": unquote(self.sec_ticket),
                "clienttype": "uasp_unicom_applet",
            }
            if hasattr(self, 'sec_jeaId'):
                headers2["Cookie"] = f"_jea_id={self.sec_jeaId}"
            res2 = self.session.post(url2, json={"activityId": "s747395186896173056", "partnersId": "1702"}, headers=headers2)
            res2 = self.session.post(url2, json={"activityId": "s747395186896173056", "partnersId": "1702"}, headers=headers2)
            for cookie in self.session.cookies:
                if cookie.name == '_jea_id':
                    self.sec_jeaId = cookie.value
            if 'Set-Cookie' in res2.headers:
                 match = re.search(r'_jea_id=([^;]+)', res2.headers['Set-Cookie'])
                 if match:
                     self.sec_jeaId = match.group(1)
                     self.log(f"安全管家: 更新 jeaId: {self.sec_jeaId}")
        except Exception as e:
            self.log(f"安全管家: getTicketForJF_sec 异常: {e}")

    def operateBlacklist_sec(self, phone_number, type_val):
        type_name = "添加" if type_val == 0 else "删除"
        self.log(f"安全管家: 正在执行{type_name}黑名单号码: {phone_number}")
        try:
            url = "https://uca.wo116114.com/sjgj/woAssistant/umm/configs/v1/config?product_line=uasp&entry_point=h5&entry_point_id=wxdefbc1986dc757a6"
            headers = {
                "User-Agent": "ChinaUnicom4.x/12.3.1 (com.chinaunicom.mobilebusiness; build:77; iOS 16.6.0) Alamofire/4.7.3 unicom{version:iphone_c@12.0301}",
                "auth-sa-token": self.sec_token,
                "clientType": "uasp_unicom_applet",
                "token": self.sec_token,
                "Cookie": f"devicedId={self.unicomTokenId}"
            }
            data = {
                "productId": "91015539",
                "type": 1,
                "operationType": type_val,
                "contents": [{ "content": phone_number, "contentTag": "", "nickname": None, "configTime": None }]
            }
            if type_val == 0:
                data["blacklistSource"] = 0
            res = self.session.post(url, json=data, headers=headers).json()
            return res
        except Exception as e:
            self.log(f"operateBlacklist_sec error: {e}")
            return None

    def addToBlacklist_sec(self):
        phone_number = "13088888888"
        res = self.operateBlacklist_sec(phone_number, 0)
        success_codes = ['0000', 0]
        if res and (res.get('code') in success_codes or res.get('msg') == '成功'):
            self.log("安全管家: ✅ 添加黑名单成功。")
            return
        is_duplicate = res and res.get('msg') and "号码已存在" in res.get('msg')
        if is_duplicate:
            self.log(f"安全管家: ⚠️ 检测到号码 {phone_number} 已存在，执行先删除后添加流程。")
            del_res = self.operateBlacklist_sec(phone_number, 1)
            is_del_success = del_res and (del_res.get('code') in success_codes or (del_res.get('msg') and ("成功" in del_res.get('msg') or "不在黑名单" in del_res.get('msg'))))
            if is_del_success:
                self.log("安全管家: ✅ 删除旧记录成功，等待 2 秒后重新添加...")
                time.sleep(2)
                retry_res = self.operateBlacklist_sec(phone_number, 0)
                if retry_res and (retry_res.get('code') in success_codes or retry_res.get('msg') == '成功'):
                    self.log("安全管家: ✅ 重新添加黑名单成功。")
                else:
                    self.log(f"安全管家: ❌ 重新添加失败: {retry_res.get('msg')}")
            else:
                self.log("安全管家: ❌ 删除旧记录失败，无法继续添加。")
        else:
            self.log(f"安全管家: ❌ 添加黑名单失败: {res.get('msg') if res else '无响应'}")

    def markPhoneNumber_sec(self):
        try:
            url = "https://uca.wo116114.com/sjgj/unicomAssistant/uasp/configs/v1/addressBook/saveTagPhone?product_line=uasp&entry_point=h5&entry_point_id=wxdefbc1986dc757a6"
            headers = {
                "User-Agent": "ChinaUnicom4.x/12.3.1 (com.chinaunicom.mobilebusiness; build:77; iOS 16.6.0) Alamofire/4.7.3 unicom{version:iphone_c@12.0301}",
                "auth-sa-token": self.sec_token,
                "clientType": "uasp_unicom_applet"
            }
            data = { "tagPhoneNo": "13088330789", "tagIds": [26], "status": 0, "productId": "91311616" }
            self.session.post(url, json=data, headers=headers)
            self.log("安全管家: 执行号码标记。")
        except Exception as e:
            self.log(f"markPhoneNumber_sec error: {e}")

    def syncAddressBook_sec(self):
        try:
            url = "https://uca.wo116114.com/sjgj/unicomAssistant/uasp/configs/v1/addressBookBatchConfig?product_line=uasp&entry_point=h5&entry_point_id=edop_unicom_3a6cc75a"
            headers = {
                "User-Agent": "ChinaUnicom4.x/12.3.1 (com.chinaunicom.mobilebusiness; build:77; iOS 16.6.0) Alamofire/4.7.3 unicom{version:iphone_c@12.0301}",
                "auth-sa-token": self.sec_token,
                "clientType": "uasp_unicom_applet"
            }
            data = { "addressBookDTOList": [{ "addressBookPhoneNo": "13088888888", "addressBookName": "水水" }], "productId": "91311616", "opType": "1" }
            self.session.post(url, json=data, headers=headers)
            self.log("安全管家: 执行同步通讯录。")
        except Exception as e:
             self.log(f"syncAddressBook_sec error: {e}")

    def setInterceptionRules_sec(self):
        try:
            url = "https://uca.wo116114.com/sjgj/woAssistant/umm/configs/v1/config?product_line=uasp&entry_point=h5&entry_point_id=wxdefbc1986dc757a6"
            headers = {
                "User-Agent": "ChinaUnicom4.x/12.3.1 (com.chinaunicom.mobilebusiness; build:77; iOS 16.6.0) Alamofire/4.7.3 unicom{version:iphone_c@12.0301}",
                "auth-sa-token": self.sec_token,
                "clientType": "uasp_unicom_applet"
            }
            data = { "contents": [{ "name": "rings-once", "contentTag": "8", "contentName": "响一声", "content": "0", "icon": "alerting" }], "operationType": 0, "type": 3, "productId": "91311616" }
            self.session.post(url, json=data, headers=headers)
            self.log("安全管家: 执行设置拦截规则。")
        except Exception as e:
             self.log(f"setInterceptionRules_sec error: {e}")

    def viewWeeklyStatus_sec(self):
        try:
            url = "https://uca.wo116114.com/sjgj/unicomAssistant/uasp/configs/v1/weeklySwitchStatus?product_line=uasp&entry_point=h5&entry_point_id=wxdefbc1986dc757a6"
            headers = { "auth-sa-token": self.sec_token, "clientType": "uasp_unicom_applet" }
            self.session.post(url, json={ "productId": "91311616" }, headers=headers)
        except: pass

    def queryKeyData_sec(self):
        try:
            url = "https://uca.wo116114.com/sjgj/unicomAssistant/uasp/report/v1/queryKeyData?product_line=uasp&entry_point=h5&entry_point_id=wxdefbc1986dc757a6"
            headers = { "auth-sa-token": self.sec_token, "clientType": "uasp_unicom_applet" }
            self.session.post(url, json={ "productId": "91311616" }, headers=headers)
        except: pass

    def viewWeeklySummary_sec(self):
        try:
            url = "https://uca.wo116114.com/sjgj/unicomAssistant/uasp/report/v1/weeklySummary?product_line=uasp&entry_point=h5&entry_point_id=wxdefbc1986dc757a6"
            headers = { "auth-sa-token": self.sec_token, "clientType": "uasp_unicom_applet" }
            self.session.post(url, json={ "productId": "91311616" }, headers=headers)
            self.log("安全管家: 执行查看周报。")
        except: pass

    def receivePoints_sec(self, taskCode):
        try:
            url = "https://m.jf.10010.com/jf-external-application/jftask/receive"
            headers = {
                "ticket": unquote(self.sec_ticket),
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301};ltst;OSVersion/16.6",
                "partnersid": "1702",
                "clienttype": "uasp_unicom_applet",
            }
            if hasattr(self, 'sec_jeaId') and self.sec_jeaId:
                headers["Cookie"] = f"_jea_id={self.sec_jeaId}"
            res = self.session.post(url, json={ "taskCode": taskCode }, headers=headers).json()
            if res.get('data') and res['data'].get('score'):
                self.log(f"安全管家: ✅ 领取积分成功: {res['data']['score']} ({res.get('msg')})", notify=True)
            elif res:
                self.log(f"安全管家: ❌ 领取积分失败: {res.get('msg')}")
            else:
                self.log("安全管家: ❌ 领取积分API无响应")
        except Exception as e:
            self.log(f"receivePoints_sec error: {e}")

    def finishTask_sec(self, taskCode, taskName):
        try:
            url = "https://m.jf.10010.com/jf-external-application/jftask/toFinish"
            headers = {
                "ticket": unquote(self.sec_ticket),
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301};ltst;OSVersion/16.6",
                "partnersid": "1702",
                "clienttype": "uasp_unicom_applet",
                "token": self.sec_token,
                "Cookie": f"devicedId={self.unicomTokenId}"
            }
            if hasattr(self, 'sec_jeaId') and self.sec_jeaId:
                headers["Cookie"] = f"_jea_id={self.sec_jeaId}"
            self.session.post(url, json={ "taskCode": taskCode }, headers=headers)
            self.log(f"安全管家: 开启任务 [{taskName}]")
            if taskName == "联通助理-添加黑名单":
                self.addToBlacklist_sec()
            elif taskName == "联通助理-号码标记":
                self.markPhoneNumber_sec()
            elif taskName == "联通助理-同步通讯录":
                self.syncAddressBook_sec()
            elif taskName == "联通助理-骚扰拦截设置":
                self.setInterceptionRules_sec()
            elif taskName == "联通助理-查看周报":
                self.viewWeeklyStatus_sec()
                self.queryKeyData_sec()
                self.viewWeeklySummary_sec()
        except Exception as e:
            self.log(f"finishTask_sec error: {e}")

    def signIn_sec(self, taskCode):
        try:
            url = "https://m.jf.10010.com/jf-external-application/jftask/sign"
            headers = {
                "ticket": unquote(self.sec_ticket),
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301};ltst;OSVersion/16.6",
                "partnersid": "1702",
                "clienttype": "uasp_unicom_applet",
            }
            if hasattr(self, 'sec_jeaId') and self.sec_jeaId:
                headers["Cookie"] = f"_jea_id={self.sec_jeaId}"
            res = self.session.post(url, json={ "taskCode": taskCode }, headers=headers).json()
            self.log(f"安全管家: 完成签到: {res.get('msg') if res else '状态未知'}")
        except Exception as e:
            self.log(f"signIn_sec error: {e}")

    def executeAllTasks_sec(self):
        try:
            url = "https://m.jf.10010.com/jf-external-application/jftask/taskDetail"
            headers = {
                "ticket": unquote(self.sec_ticket),
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301};ltst;OSVersion/16.6",
                "partnersid": "1702",
                "clienttype": "uasp_unicom_applet",
            }
            if hasattr(self, 'sec_jeaId') and self.sec_jeaId:
                headers["Cookie"] = f"_jea_id={self.sec_jeaId}"
            res = self.session.post(url, json={}, headers=headers).json()
            if not res or not res.get('data') or not res['data'].get('taskDetail'):
                self.log("安全管家: 查询任务列表失败或响应格式错误。")
                return
            taskList = res['data']['taskDetail']['taskList']
            executableTaskNames = [
                "联通助理-添加黑名单",
                "联通助理-号码标记",
                "联通助理-同步通讯录",
                "联通助理-骚扰拦截设置",
                "联通助理-查看周报"
            ]
            executableTasks = []
            skippedTasks = []
            for task in taskList:
                isKnown = task['taskName'] in executableTaskNames or "签到" in task['taskName']
                if isKnown:
                    executableTasks.append(task)
                else:
                    skippedTasks.append(task)
            unfinished_skipped = [t for t in skippedTasks if t['finishCount'] != t['needCount']]
            if unfinished_skipped:
                skipped_names = ", ".join([f"[{t['taskName']}]" for t in unfinished_skipped])
                self.log(f"安全管家: 跳过: {skipped_names}")
            for task in executableTasks:
                taskName = task['taskName']
                taskCode = task['taskCode']
                finishCount = int(task['finishCount'])
                needCount = int(task['needCount'])
                finishText = task.get('finishText', '')
                self.log(f"安全管家: [{taskName}]: {finishCount}/{needCount} - {finishText}")
                if finishCount != needCount:
                    remaining = needCount - finishCount
                    self.log(f"安全管家: 任务未完成，需要再执行 {remaining} 次")
                    for i in range(remaining):
                        time.sleep(3)
                        try:
                            if "签到" in taskName:
                                self.signIn_sec(taskCode)
                            else:
                                self.finishTask_sec(taskCode, taskName)
                            if "签到" not in taskName:
                                time.sleep(10)
                                self.receivePoints_sec(taskCode)
                            else:
                                self.receivePoints_sec(taskCode)
                                break
                        except Exception as e:
                            self.log(f"安全管家: 执行 {taskCode} 时出错: {e}")
                            break
                elif finishText == "待领取":
                     try:
                        time.sleep(3)
                        self.receivePoints_sec(taskCode)
                     except Exception as e:
                        self.log(f"安全管家: 领取 {taskCode} 奖励时出错: {e}")
                else:
                    self.log(f"安全管家: [{taskName}] 任务已完成且奖励已领取")
                self.log("安全管家: ---------------------")
        except Exception as e:
            self.log(f"executeAllTasks_sec error: {e}")

    def getUserInfo_sec(self):
        try:
            url = "https://m.jf.10010.com/jf-external-application/jftask/userInfo"
            headers = {
                "ticket": unquote(self.sec_ticket),
                "User-Agent": "Mozilla/5.0 (Linux; Android 9; ONEPLUS A5000 Build/PKQ1.180716.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.179 Mobile Safari/537.36",
                "partnersid": "1702",
                "clienttype": "uasp_unicom_applet",
            }
            if hasattr(self, 'sec_jeaId') and self.sec_jeaId:
                headers["Cookie"] = f"_jea_id={self.sec_jeaId}"
            res = self.session.post(url, json={}, headers=headers).json()
            if not res or res.get('code') != '0000' or not res.get('data'):
                self.log(f"安全管家: 查询积分失败: {res.get('msg') if res else '无响应'}")
                return
            currentPoints = int(res['data'].get('availableScore', 0))
            todayPoints = res['data'].get('todayEarnScore', 0)
            if not hasattr(self, 'sec_oldJFPoints') or self.sec_oldJFPoints is None:
                self.sec_oldJFPoints = currentPoints
                self.log(f"安全管家: 运行前积分：{currentPoints} (今日已赚 {todayPoints})")
            else:
                 pointsGained = currentPoints - self.sec_oldJFPoints
                 self.log(f"安全管家: 运行后积分{currentPoints}，本次运行获得{pointsGained}", notify=True)
        except Exception as e:
            self.log(f"getUserInfo_sec error: {e}")

    def securityButlerTask(self, is_query_only=False):
        self.log("==== 联通安全管家 ====")
        if not self.ecs_token:
            self.log("安全管家: 缺少 ecs_token，跳过")
            return
        try:
            self.getTicketByNative_sec()
            if not getattr(self, 'sec_ticket1', None): return
            self.getAuthToken_sec()
            if not getattr(self, 'sec_token', None): return
            self.getTicketForJF_sec()
            if not getattr(self, 'sec_ticket', None): return
            self.sec_oldJFPoints = None
            self.getUserInfo_sec()
            if is_query_only:
                self.log("安全管家: [查询模式] 跳过任务执行...")
                return
            self.executeAllTasks_sec()
            self.getUserInfo_sec()
        except Exception as e:
            self.log(f"安全管家: 异常: {e}")

    def aiting_query_integral(self):
        url = "https://m.jf.10010.com/jf-external-application/jftask/userInfo"
        headers = {
            'ticket': self.aiting_biz_ticket,
            'pageid': 's789081246969976832',
            'clienttype': 'aiting_android',
            'partnersid': '1706',
            'content-type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Redmi K30 Pro Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.159 Mobile Safari/537.36 WoReaderApp/Android',
            'Origin': 'https://m.jf.10010.com'
        }
        res = self.session.post(url, json={}, headers=headers).json()
        if res.get('code') == '0000':
             data = res.get('data', {})
             self.log(f"积分概览: 今日已赚 {data.get('todayEarnScore')}, 当前余额 {data.get('availableScore')}", notify=True)

    def ltzf_task(self):
        self.log("==== 联通祝福 ====")
        base_url = "https://wocare.unisk.cn/mbh/getToken"
        params = {
            "channelType": WOCARE_CONSTANTS["serviceLife"],
            "homePage": "home",
            "duanlianjieabc": "qAz2m"
        }
        targetUrl = f"{base_url}?{urlencode(params)}"
        res = self.openPlatLineNew(targetUrl)
        if not res or 'ticket' not in res:
            self.log("联通祝福: 获取Ticket失败")
            return
        ticket = res['ticket']
        if not self.wocare_getToken(ticket):
            self.log("联通祝福: 获取Wocare Token失败")
            return
        self.wocare_getSpecificityBanner()
        wocare_activities = [
            {"name": "星座配对", "id": 2},
            {"name": "大转盘", "id": 3},
            {"name": "盲盒抽奖", "id": 4}
        ]
        for activity in wocare_activities:
            self.wocare_getDrawTask(activity)
            self.wocare_loadInit(activity)

    def openPlatLineNew(self, to_url):
        try:
            base_url = "https://m.client.10010.com/mobileService/openPlatform/openPlatLineNew.htm"
            params = {"to_url": to_url}
            for attempt in range(1, 4):
                try:
                    res = self.session.get(base_url, params=params, allow_redirects=False, timeout=15)
                    break
                except Exception as e:
                    err_msg = str(e)
                    if attempt < 3 and os.environ.get("UNICOM_PROXY_API") and ("Max retries exceeded" in err_msg or "timed out" in err_msg.lower() or "connection" in err_msg.lower() or "SOCKS" in err_msg):
                        self.log(f"openPlatLineNew 第{attempt}次异常触发故障转移: {err_msg}")
                        self.failover_proxy()
                        continue
                    self.log(f"openPlatLineNew 第{attempt}次重试 - 异常: {e}")
                    if attempt == 3:
                         return None
                    time.sleep(2)
            if res.status_code == 302 and 'Location' in res.headers:
                loc = res.headers['Location']
                parsed = urlparse(loc)
                qs = parse_qs(parsed.query)
                ticket = qs.get('ticket', [''])[0]
                type_val = qs.get('type', [''])[0]
                if ticket:
                    return {'ticket': ticket, 'type': type_val, 'loc': loc}
                else:
                    self.log("openPlatLineNew: 重定向URL中无ticket")
            else:
                self.log(f"openPlatLineNew: 状态码{res.status_code} (期望302)")
        except Exception as e:
            self.log(f"openPlatLineNew 异常: {str(e)}")
        return None

    def random_string(self, length, chars=string.ascii_letters + string.digits):
        return ''.join(random.choice(chars) for _ in range(length))

    def get_bizchannelinfo(self):
        info = {
            "bizChannelCode": "225",
            "disriBiz": "party",
            "unionSessionId": "",
            "stType": "",
            "stDesmobile": "",
            "source": "",
            "rptId": self.rptId,
            "ticket": "",
            "tongdunTokenId": self.tokenId_cookie,
            "xindunTokenId": self.unicomTokenId
        }
        return json.dumps(info)

    def get_epay_authinfo(self):
        info = {
            "mobile": "",
            "sessionId": getattr(self, 'sessionId', ''),
            "tokenId": getattr(self, 'tokenId', ''),
            "userId": ""
        }
        return json.dumps(info)

    def ttlxj_task(self, is_query_only=False):
        self.log("==== 天天领现金 ====")
        for attempt in range(1, 31):
            try:
                ticket_res = self.openPlatLineNew("https://epay.10010.com/ci-mps-st-web/ttlxj/")
                if not ticket_res or not ticket_res.get('ticket'):
                    if attempt < 30:
                        self.log(f"天天领现金: 获取Ticket失败，正在重试 ({attempt}/30)...")
                        time.sleep(2)
                        continue
                    else:
                        self.log("天天领现金: 获取Ticket失败，已达最大重试次数，跳过任务")
                        return
                ticket = ticket_res['ticket']
                type_val = ticket_res['type']
                if self.ttlxj_authorize(ticket, type_val, ticket_res['loc']):
                    if self.ttlxj_auth_check():
                         if is_query_only:
                            self.ttlxj_query_available()
                            return
                         self.ttlxj_do_tasks()
                         self.ttlxj_query_available()
                         break
                else:
                     if attempt < 30:
                        self.log(f"天天领现金: 授权失败，正在重试 ({attempt}/30)...")
                        time.sleep(2)
                     else:
                        self.log("天天领现金: 授权失败，已达最大重试次数")
            except Exception as e:
                if attempt < 30:
                    self.log(f"天天领现金: 任务异常 ({e})，正在重试 ({attempt}/30)...")
                    time.sleep(2)
                else:
                    self.log(f"天天领现金: 任务异常: {e}")

    def ttlxj_authorize(self, ticket, type_val, referer_url):
        try:
            url = "https://epay.10010.com/woauth2/v2/authorize"
            headers = {
                "Origin": "https://epay.10010.com",
                "Referer": referer_url
            }
            payload = {
                "response_type": "rptid",
                "client_id": "73b138fd-250c-4126-94e2-48cbcc8b9cbe",
                "redirect_uri": "https://epay.10010.com/ci-mps-st-web/",
                "login_hint": {
                    "credential_type": "st_ticket",
                    "credential": ticket,
                    "st_type": type_val,
                    "force_logout": True,
                    "source": "app_sjyyt"
                },
                "device_info": {
                    "token_id": f"chinaunicom-pro-{int(time.time()*1000)}-{self.random_string(13)}",
                    "trace_id": self.random_string(32)
                }
            }
            res = self.session.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                return True
            else:
                self.log(f"天天领现金: Authorize失败[{res.status_code}]: {res.text}")
                return False
        except Exception as e:
             self.log(f"ttlxj_authorize error: {e}")
             return False

    def ttlxj_auth_check(self):
        try:
            url = "https://epay.10010.com/ps-pafs-auth-front/v1/auth/check"
            headers = {
                "bizchannelinfo": self.get_bizchannelinfo()
            }
            res = self.session.post(url, headers=headers, json={}, timeout=10)
            data = res.json()
            code = data.get("code")
            if code == "0000":
                auth_info = data.get("data", {}).get("authInfo", {})
                self.sessionId = auth_info.get("sessionId", "")
                self.tokenId = auth_info.get("tokenId", "")
                self.epay_userId = auth_info.get("userId", "")
                return True
            elif code == "2101000100":
                login_url = data.get("data", {}).get("woauth_login_url")
                if login_url:
                    return self.ttlxj_login(login_url)
            else:
                self.log(f"天天领现金: AuthCheck失败[{code}]: {data.get('msg')}")
                return False
        except Exception as e:
            self.log(f"ttlxj_auth_check error: {e}")
            return False

    def ttlxj_login(self, login_url):
        try:
            full_url = f"{login_url}https://epay.10010.com/ci-mcss-party-web/clockIn/?bizFrom=225&bizChannelCode=225"
            res = self.session.get(full_url, allow_redirects=False, timeout=10)
            if res.status_code == 302 and 'Location' in res.headers:
                loc = res.headers['Location']
                parsed = urlparse(loc)
                qs = parse_qs(parsed.query)
                rptid = qs.get('rptid', [''])[0]
                if rptid:
                    self.rptId = rptid
                    return self.ttlxj_auth_check()
                else:
                    self.log("天天领现金: Login跳转后无rptid")
            else:
                self.log(f"天天领现金: Login失败[{res.status_code}]")
            return False
        except Exception as e:
            self.log(f"ttlxj_login error: {e}")
            return False

    def ttlxj_do_tasks(self):
        info_url = "https://epay.10010.com/ci-mcss-party-front/v1/ttlxj/userDrawInfo"
        headers = {
            "bizchannelinfo": self.get_bizchannelinfo(),
            "authinfo": self.get_epay_authinfo()
        }
        res = self.request("post", info_url, json={}, headers=headers)
        if not res: return
        data = res.json()
        if data.get('code') == '0000':
            day_of_week = data.get("data", {}).get("dayOfWeek", "")
            draw_key = f"day{day_of_week}"
            has_not_clocked_in = data.get("data", {}).get(draw_key) == "1"
            if has_not_clocked_in:
                self.log(f"天天领现金: 今天未打卡", notify=True)
                today_js = (datetime.now().weekday() + 1) % 7
                draw_type = "C" if today_js == 0 else "B"
                self.ttlxj_unifyDrawNew(draw_type)
            else:
                 self.log(f"天天领现金: 今天已打卡", notify=True)
        else:
            self.log(f"天天领现金: 查询失败: {data.get('msg')}")

    def ttlxj_unifyDrawNew(self, draw_type):
        draw_url = "https://epay.10010.com/ci-mcss-party-front/v1/ttlxj/unifyDrawNew"
        headers = {
            "bizchannelinfo": self.get_bizchannelinfo(),
            "authinfo": self.get_epay_authinfo()
        }
        req_data = {
            "drawType": draw_type,
            "bizFrom": "225",
            "activityId": "TTLXJ20210330"
        }
        res = self.request("post", draw_url, data=req_data, headers=headers)
        if not res: return
        data = res.json()
        if data.get('code') == '0000':
            prize = data.get('data', {}).get('prizeName', '未知奖品')
            self.log(f"天天领现金: 抽奖成功: {prize}", notify=True)
        else:
            self.log(f"天天领现金: 抽奖失败: {data.get('msg')}")

    def ttlxj_query_available(self):
        avail_url = "https://epay.10010.com/ci-mcss-party-front/v1/ttlxj/queryAvailable"
        headers = {
            "bizchannelinfo": self.get_bizchannelinfo(),
            "authinfo": self.get_epay_authinfo()
        }
        res = self.request("post", avail_url, json={}, headers=headers)
        if not res: return
        data = res.json()
        if data.get('code') == '0000':
            d = data.get('data', {})
            amount_raw = int(d.get('availableAmount', '0'))
            amount_yuan = f"{amount_raw / 100:.2f}"
            msg = f"天天领现金: 可用立减金: {amount_yuan}元"
            seven_day = int(d.get('sevenDayExpireAmount', 0))
            if seven_day > 0:
                msg += f", 7天内过期立减金: {seven_day / 100:.2f}元"
            min_exp_amt = int(d.get('minExpireAmount', 0))
            min_exp_date = d.get('minExpireDate')
            if min_exp_amt > 0 and min_exp_date:
                msg += f", 最早过期立减金: {min_exp_amt / 100:.2f}元 -- {min_exp_date}过期"
            self.log(msg, notify=True)
        else:
            self.log(f"天天领现金: 查询余额失败: {data.get('msg')}")

    def aiting_get_aes(self, data, key):
        iv_str = "16-Bytes--String"
        key_bytes = key[:16].encode('utf-8')
        iv_bytes = iv_str[:16].encode('utf-8')
        text = json.dumps(data, separators=(',', ':')) if isinstance(data, (dict, list)) else str(data)
        padded_data = pad(text.encode('utf-8'), 16)
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        ciphertext = cipher.encrypt(padded_data)
        hex_str = ciphertext.hex()
        return base64.b64encode(hex_str.encode('utf-8')).decode('utf-8')

    def aiting_aes_encrypt(self, data, key, iv):
        key_bytes = key.encode('utf-8')
        iv_bytes = iv.encode('utf-8')
        text = json.dumps(data, separators=(',', ':')) if isinstance(data, (dict, list)) else str(data)
        padded_data = pad(text.encode('utf-8'), 16)
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        ciphertext = cipher.encrypt(padded_data)
        hex_str = ciphertext.hex().upper()
        return base64.b64encode(hex_str.encode('utf-8')).decode('utf-8')

    def aiting_md5(self, text):
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def aiting_generate_sign(self, params, key):
        sorted_keys = sorted(params.keys())
        sign_str = '&'.join([f"{k}={params[k]}" for k in sorted_keys])
        final_str = f"{sign_str}&key={key}"
        return self.aiting_md5(final_str)

    def aiting_timestamp(self):
        return str(int(time.time() * 1000))

    def aiting_nonce(self):
        return str(random.randint(100000, 999999))

    def aiting_generate_woid(self, imei):
        random6 = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        imei8 = imei[:8] if len(imei) >= 8 else imei.ljust(8, '0')
        random4 = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
        random2 = ''.join(random.choices(string.ascii_letters + string.digits, k=2))
        return f"WOA{random6}{imei8}LOT{random4}LV{random2}"

    def aiting_calculate_clientconfirm(self, userid, imei):
        plaintext = f"android{userid}{imei}"
        return self.aiting_aes_encrypt(plaintext, AITING_AES_KEY, AITING_AES_IV)

    def aiting_calculate_passcode(self, timestamp, phone):
        return self.aiting_md5(timestamp + phone + AITING_CLIENT_KEY)

    def aiting_build_statisticsinfo(self, userid, useraccount, imei, clientconfirm):
        params = {
            'channelid': '28015001',
            'sid': ''.join(random.choices(string.ascii_letters + string.digits + "_-", k=20)),
            'eid': ''.join(random.choices(string.ascii_letters + string.digits + "_", k=20)),
            'osversion': 'Android12',
            'clientallid': '000000100000000000058.0.2.1225',
            'display': '2400_1080',
            'ip': '192.168.3.24',
            'nettypename': 'wifi',
            'version': '802',
            'versionname': '8.0.2',
            'terminalName': 'Redmi',
            'terminalType': 'Redmi_K30_Pro',
            'udid': 'null',
            'woid': self.aiting_generate_woid(imei),
            'useraccount': useraccount,
            'userid': userid,
            'clientconfirm': clientconfirm
        }
        return '&'.join([f"{k}={params[k]}" for k in params])

    def generate_random_imei(self):
        tac = ''.join([str(random.randint(0, 9)) for _ in range(8)])
        snr = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        imei_raw = tac + snr
        digits = [int(d) for d in imei_raw]
        for i in range(len(digits) - 1, -1, -2):
            digits[i] *= 2
            if digits[i] > 9: digits[i] -= 9
        total = sum(digits)
        check_digit = (10 - (total % 10)) % 10
        return imei_raw + str(check_digit)

    def aiting_woread_login(self, phone):
        access_token = "ODZERTZCMjA1NTg1MTFFNDNFMThDRDYw"
        token_enc = ""
        if self.token_online:
             token_enc = self.aiting_get_aes(self.token_online, WOREAD_KEY)
        else:
             self.log("阅读专区: 未找到 token_online，尝试仅使用手机号登录")
        phone_enc = self.aiting_get_aes(phone, WOREAD_KEY)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        if token_enc:
            inner_data = {
                "tokenOnline": token_enc,
                "phone": phone_enc,
                "timestamp": timestamp
            }
        else:
            inner_data = {
                "phone": phone_enc,
                "timestamp": timestamp
            }
        sign_result = self.aiting_get_aes(inner_data, WOREAD_KEY)
        url = "https://10010.woread.com.cn/ng_woread_service/rest/account/login"
        body = {"sign": sign_result}
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 11; Redmi Note 10 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.159 Mobile Safari/537.36",
            "accesstoken": access_token,
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://10010.woread.com.cn"
        }
        res = self.session.post(url, json=body, headers=headers).json()
        if res.get("code") == "0000":
            return res.get("data", {}).get("token")
        self.log(f"爱听登录: 沃阅读登录失败: {res}")
        return None

    def aiting_get_jwt_token(self, statisticsinfo):
        timestamp = self.aiting_timestamp()
        sign_params = {
            'clientSource': '3',
            'clientId': 'android',
            'source': '3',
            'timestamp': timestamp
        }
        sign_val = self.aiting_generate_sign(sign_params, AITING_SIGN_KEY_APPKEY)
        client_id_const = "395DEDE9C1D6FE11B7C9C0D82B353E74"
        client_id_b64 = base64.b64encode(client_id_const.encode('utf-8')).decode('utf-8')
        body = {
            'clientSource': '3',
            'clientId': client_id_b64,
            'source': '3',
            'timestamp': timestamp,
            'sign': sign_val
        }
        url = f"{AITING_BASE_URL}/oauth/client/appkey"
        headers = {
            'Skip-Authorization-Check': 'true',
            'statisticsinfo': statisticsinfo,
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; Redmi K30 Pro Build/SKQ1.220303.001)"
        }
        try:
            res = self.session.post(url, json=body, headers=headers).json()
            if res.get("code") == "0000" and res.get("key"):
                return res.get("key")
            self.log(f"爱听登录: 获取JWT失败: {res}")
        except Exception as e:
            self.log(f"爱听登录: 获取JWT异常: {e}")
        return None

    def aiting_api_login(self, phone, useraccount, jwt_token, statisticsinfo):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        passcode = self.aiting_calculate_passcode(timestamp, phone)
        query_params_list = [
            'networktype=3', 'ua=Redmi+K30+Pro', 'isencode=false',
            'clientversion=8.0.2', 'versionname=Android_1_1080x2356',
            'channelid=28015001', 'userlabelisencode=0', 'validatecode=', 'sid=',
            f"timestamp={timestamp}", f"passcode={passcode}"
        ]
        query_str = '&'.join(query_params_list)
        final_account = useraccount
        url = f"{AITING_BASE_URL}/mainrest/rest/read/user/ulogin/3/{final_account}/1/1/0?{query_str}"
        req_time = self.aiting_timestamp()
        nonce = self.aiting_nonce()
        sign_params = {
            'jwt': jwt_token,
            'nonestr': nonce,
            'osversion': 'Android12',
            'terminalName': 'Redmi',
            'timestamp': req_time
        }
        sorted_keys = sorted(sign_params.keys())
        sign_str = '&'.join([f"{k}={sign_params[k]}" for k in sorted_keys])
        requertid = self.aiting_md5(f"{sign_str}&key={AITING_SIGN_KEY_REQUERTID}")
        headers = {
            'statisticsinfo': statisticsinfo,
            'requerttime': req_time,
            'nonestr': nonce,
            'requertid': requertid,
            'AuthorizationClient': f"Bearer {jwt_token}",
            'User-Agent': 'okhttp/4.9.0'
        }
        try:
            res = self.session.get(url, headers=headers).json()
            if res.get("code") == "0000" and res.get("message"):
                msg = res.get("message")
                token = msg.get("token")
                userid = msg.get("userid")
                if msg.get("accountinfo"):
                    token = msg.get("accountinfo", {}).get("token") or token
                    userid = msg.get("accountinfo", {}).get("userid") or userid
                return {"token": token, "userid": userid}
            self.log(f"爱听登录: 业务API登录失败: {res}")
        except Exception as e:
            self.log(f"爱听登录: 业务API异常: {e}")
        return None

    def aiting_login_flow(self):
        self.log("正在执行爱听登录流程...")
        woread_token = self.aiting_woread_login(self.mobile)
        if not woread_token: return False
        self.aiting_woread_token = woread_token
        imei = self.generate_random_imei()
        userid = self.mobile
        useraccount = self.mobile
        clientconfirm = self.aiting_calculate_clientconfirm(userid, imei)
        statisticsinfo = self.aiting_build_statisticsinfo(userid, useraccount, imei, clientconfirm)
        self.aiting_statisticsinfo = statisticsinfo
        jwt = self.aiting_get_jwt_token(statisticsinfo)
        if not jwt: return False
        self.aiting_jwt = jwt
        login_data = self.aiting_api_login(self.mobile, useraccount, jwt, statisticsinfo)
        if not login_data: return False
        self.aiting_biz_token = login_data.get('token')
        self.aiting_base_userid = login_data.get('userid') or self.mobile
        self.log(f"✅ 爱听业务登录成功! Token已获取")
        biz_ticket = self.aiting_get_ticket()
        if biz_ticket:
            self.aiting_biz_ticket = biz_ticket
            return True
        return False

    def aiting_get_ticket(self):
        url = f"{AITING_BASE_URL}/activity/rest/unicom/points/getInfoTicket"
        timestamp = self.aiting_timestamp()
        sign_params = {
            "token": self.aiting_biz_token,
            "timestamp": timestamp,
            "userid": self.aiting_base_userid
        }
        sign_val = self.aiting_generate_sign(sign_params, AITING_SIGN_KEY_API)
        body = {
            "sign": sign_val,
            "timestamp": timestamp,
            "token": self.aiting_biz_token,
            "userid": self.aiting_base_userid
        }
        nonce = self.aiting_nonce()
        head_sign_params = {
            'jwt': self.aiting_jwt,
            'nonestr': nonce,
            'osversion': 'Android12',
            'terminalName': 'Redmi',
            'timestamp': timestamp
        }
        sorted_keys = sorted(head_sign_params.keys())
        sign_str = '&'.join([f"{k}={head_sign_params[k]}" for k in sorted_keys])
        final_sign_str = f"{sign_str}&key={AITING_SIGN_KEY_REQUERTID}"
        requertid = self.aiting_md5(final_sign_str)
        headers = {
            "AuthorizationClient": f"Bearer {self.aiting_jwt}",
            "statisticsinfo": self.aiting_statisticsinfo,
            "requerttime": timestamp,
            "nonestr": nonce,
            "requertid": requertid
        }
        try:
            res = self.session.post(url, json=body, headers=headers).json()
            if res.get("code") == "0000":
                msg = res.get("message", "")
                if "ticket=" in msg:
                    match = re.search(r'ticket=([^&]+)', msg)
                    if match:
                        return match.group(1)
                return msg # Fallback if message is ticket itself? No, standard is URL.
            self.log(f"爱听登录: 获取Ticket失败: {res}")
        except Exception as e:
            self.log(f"爱听登录: 获取Ticket异常: {e}")
        return None

    def jf_get_task_detail(self, ticket):
        url = "https://m.jf.10010.com/jf-external-application/jftask/taskDetail"
        headers = {
            'ticket': ticket,
            'pageid': 's789081246969976832',
            'clienttype': 'aiting_android',
            'partnersid': '1706',
            'content-type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Redmi K30 Pro Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.159 Mobile Safari/537.36 WoReaderApp/Android',
            'Origin': 'https://m.jf.10010.com',
            'Referer': f"https://m.jf.10010.com/jf-external-application/index.html?ticket={ticket}&pageID=s789081246969976832"
        }
        res = self.session.post(url, json={}, headers=headers).json()
        return res.get("data", {}).get("taskDetail", {}).get("taskList", [])

    def jf_to_finish(self, ticket, task_code):
        url = "https://m.jf.10010.com/jf-external-application/jftask/toFinish"
        headers = {
            'ticket': ticket,
            'pageid': 's789081246969976832',
            'clienttype': 'aiting_android',
            'partnersid': '1706',
            'content-type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Redmi K30 Pro Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.159 Mobile Safari/537.36 WoReaderApp/Android',
            'Origin': 'https://m.jf.10010.com'
        }
        self.session.post(url, json={'taskCode': task_code}, headers=headers)

    def jf_pop_up(self, ticket):
        url = "https://m.jf.10010.com/jf-external-application/jftask/popUp"
        headers = {
            'ticket': ticket,
            'pageid': 's789081246969976832',
            'clienttype': 'aiting_android',
            'partnersid': '1706',
            'content-type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Redmi K30 Pro Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.159 Mobile Safari/537.36 WoReaderApp/Android',
            'Origin': 'https://m.jf.10010.com'
        }
        res = self.session.post(url, json={}, headers=headers).json()
        if isinstance(res, dict):
            if res.get('code') == "0000" and res.get('data', {}).get('score'):
                self.log(f"  └─ 🎉 获得 {res['data']['score']} 积分", notify=True)
            elif res.get('code') != "0000":
                self.log(f"  └─ 📝 积分弹窗返回: {res.get('desc', res)}")
        return res

    def aiting_complete_task_api(self, type_val):
        timestamp = self.aiting_timestamp()
        nonce = self.aiting_nonce()
        sign_params = {'jwt': self.aiting_jwt, 'nonestr': nonce, 'osversion': 'Android12', 'terminalName': 'Redmi', 'timestamp': timestamp}
        sign_str = '&'.join([f"{k}={sign_params[k]}" for k in sorted(sign_params.keys())])
        requertid = self.aiting_md5(f"{sign_str}&key={AITING_SIGN_KEY_REQUERTID}")
        body_params = {'source': '3', 'timestamp': timestamp, 'token': self.aiting_woread_token, 'type': str(type_val), 'userid': self.aiting_base_userid}
        body_str = '&'.join([f"{k}={body_params[k]}" for k in sorted(body_params.keys())])
        sign = self.aiting_md5(f"{body_str}&key={AITING_SIGN_KEY_API}")
        url = f"{AITING_BASE_URL}/activity/rest/unicom/points/completiontask"
        payload = {**body_params, 'sign': sign}
        headers = {
            'AuthorizationClient': f"Bearer {self.aiting_jwt}",
            'requerttime': timestamp,
            'nonestr': nonce,
            'requertid': requertid,
            'statisticsinfo': self.aiting_statisticsinfo
        }
        self.session.post(url, json=payload, headers=headers)

    def aiting_get_secretkey(self):
        timestamp = self.aiting_timestamp()
        nonce = self.aiting_nonce()
        sign_params = {'jwt': self.aiting_jwt, 'nonestr': nonce, 'osversion': 'Android12', 'terminalName': 'Redmi', 'timestamp': timestamp}
        sign_str = '&'.join([f"{k}={sign_params[k]}" for k in sorted(sign_params.keys())])
        requertid = self.aiting_md5(f"{sign_str}&key={AITING_SIGN_KEY_REQUERTID}")
        url = f"https://woread.com.cn/rest/read/statistics/getsecretkey/3/{self.aiting_base_userid}"
        headers = {
            'AuthorizationClient': f"Bearer {self.aiting_jwt}",
            'requerttime': timestamp, 'nonestr': nonce, 'requertid': requertid,
            'statisticsinfo': self.aiting_statisticsinfo, 'User-Agent': 'okhttp/4.9.0'
        }
        params = {'token': self.aiting_woread_token}
        res = self.session.get(url, params=params, headers=headers).json()
        if res.get("code") == "0000":
            return res.get("message")
        return None

    def aiting_add_read_time(self, read_time_seconds):
        secretkey = self.aiting_get_secretkey()
        if not secretkey: return
        timestamp = self.aiting_timestamp()
        count_time_str = str(read_time_seconds * 1000)
        book_id = "4524960"
        data_obj = {
            "userid": self.aiting_base_userid,
            "counttime": count_time_str,
            "timestamp": timestamp,
            "secretkey": secretkey,
            "cntindex": book_id,
            "cnttype": 1,
            "readtype": 1
        }
        encrypted = self.aiting_aes_encrypt(data_obj, ADDREADTIME_AES_KEY, AITING_AES_IV)
        nonce = self.aiting_nonce()
        sign_params = {'jwt': self.aiting_jwt, 'nonestr': nonce, 'osversion': 'Android12', 'terminalName': 'Redmi', 'timestamp': timestamp}
        sign_str = '&'.join([f"{k}={sign_params[k]}" for k in sorted(sign_params.keys())])
        requertid = self.aiting_md5(f"{sign_str}&key={AITING_SIGN_KEY_REQUERTID}")
        url = f"https://woread.com.cn/rest/read/statistics/addreadtime/3/{encrypted}"
        random_uuid = str(uuid.uuid4()).replace('-', '')
        body = {
            "channelid": "28015001", "creadertime": datetime.now().strftime("%y%m%d%H%M%S"),
            "imei": self.generate_random_imei(),
            "list": { "cntindex": book_id, "cnttype": 1, "readtime": count_time_str, "readtype": 1 },
            "list1": [{ "cntindex": book_id, "cnttype": 1, "readtime": count_time_str, "readtype": 1 }],
            "listentimes": count_time_str, "uuid": random_uuid
        }
        headers = {
            'AuthorizationClient': f"Bearer {self.aiting_jwt}",
            'requerttime': timestamp, 'nonestr': nonce, 'requertid': requertid,
            'statisticsinfo': self.aiting_statisticsinfo, 'User-Agent': 'okhttp/4.9.0'
        }
        res = self.session.post(url, json=body, headers=headers)
        if res.status_code == 200:
             self.last_read_submission_time = time.time()
             self.log(f"✅ 阅读时长上报成功 ({read_time_seconds}s)")

    def aiting_new_read_add(self):
        timestamp = self.aiting_timestamp()
        nonce = self.aiting_nonce()
        sign_params = {'jwt': self.aiting_jwt, 'nonestr': nonce, 'osversion': 'Android12', 'terminalName': 'Redmi', 'timestamp': timestamp}
        sign_str = '&'.join([f"{k}={sign_params[k]}" for k in sorted(sign_params.keys())])
        requertid = self.aiting_md5(f"{sign_str}&key={AITING_SIGN_KEY_REQUERTID}")
        url = f"https://woread.com.cn/rest/read/new/newreadadd/3/{self.aiting_base_userid}/{self.aiting_woread_token}"
        params = {'isfreeLimt': '0', 'isgray': 'true'}
        body = {"source": 3, "cntindex": "4524960", "chapterallindex": "100136247350", "readtype": 3}
        headers = {
             'AuthorizationClient': f"Bearer {self.aiting_jwt}", 'requerttime': timestamp, 'nonestr': nonce, 'requertid': requertid, 'statisticsinfo': self.aiting_statisticsinfo, 'User-Agent': 'Redmi K30 Pro'
        }
        self.session.post(url, params=params, json=body, headers=headers)

    def aiting_task(self, is_query_only=False):
        self.log("==== 联通爱听任务 ====")
        if not self.aiting_login_flow():
            self.log("爱听任务: 登录失败，跳过")
            return
        self.log("爱听任务: 登录成功，正在获取任务列表...")
        try:
            self.aiting_query_integral()
        except: pass
        task_list = self.jf_get_task_detail(self.aiting_biz_ticket)
        done_list = [t for t in task_list if t.get('finish') == 1]
        printed_names = set()
        for t in done_list:
             name = t.get('taskName')
             if name not in printed_names:
                 self.log(f"  ✅ {name} ({t.get('finishCount')}/{t.get('needCount')})")
                 printed_names.add(name)
        todo_list = [t for t in task_list if t.get('finish') == 0 and "邀请" not in t.get('taskName', '')]
        if not todo_list:
            self.log("爱听任务: ✅ 所有任务已完成")
            if is_query_only:
                self.log("爱听任务: [查询模式] 跳过任务执行...")
            return
        self.log(f"爱听任务: 发现 {len(todo_list)} 个待办任务")
        if is_query_only:
            self.log("爱听任务: [查询模式] 跳过任务执行...")
            return
        read_tasks = [t for t in todo_list if ("阅读" in t.get('taskName','') or "听读" in t.get('taskName','')) and "邀请" not in t.get('taskName','')]
        for task in read_tasks:
            remaining = int(task.get('needCount', 1)) - int(task.get('finishCount', 0))
            if remaining <= 0: continue
            self.log(f"执行阅读任务: {task.get('taskName')} (剩余 {remaining} 次)")
            for i in range(remaining):
                self.jf_to_finish(self.aiting_biz_ticket, task.get('taskCode'))
                self.log(f"  └─ 第 {i + 1}/{remaining} 次: 极速提交中...")
                self.aiting_new_read_add()
                time.sleep(5)
                self.aiting_add_read_time(120)
                time.sleep(2)
                self.jf_pop_up(self.aiting_biz_ticket)
        other_tasks = [t for t in todo_list if not any(x in t.get('taskName','') for x in ["通知", "阅读", "听读", "邀请", "签到"])]
        notify_task = next((t for t in todo_list if "通知" in t.get('taskName','')), None)
        if notify_task:
            self.log(f"执行通知任务: {notify_task.get('taskName')}")
            self.jf_to_finish(self.aiting_biz_ticket, notify_task.get('taskCode'))
            time.sleep(1)
            self.aiting_complete_task_api(2)
            time.sleep(2)
            self.jf_pop_up(self.aiting_biz_ticket)
        for task in other_tasks:
            remaining = int(task.get('needCount', 1)) - int(task.get('finishCount', 0))
            if remaining <= 0: continue
            self.log(f"执行通用任务: {task.get('taskName')} (剩余 {remaining} 次)")
            for i in range(remaining):
                 self.jf_to_finish(self.aiting_biz_ticket, task.get('taskCode'))
                 time.sleep(1.5)
                 self.aiting_complete_task_api(4) # Type 4
                 time.sleep(2)
                 self.jf_pop_up(self.aiting_biz_ticket)
        try:
            self.aiting_query_integral()
        except: pass

    def wostore_cloud_login(self, ticket):
        try:
            url1 = "https://member.zlhz.wostore.cn/wcy_member/yunPhone/h5Awake/businessHall"
            body1 = {
                "cpId": "91002997", "channelId": "ST-Zujian001-gs", "ticket": ticket,
                "env": "prod", "transId": "S2ndpage1235+开福袋！+F1+CJDD00D0001+iphone_c@12.0801",
                "qkActId": None
            }
            headers1 = {"Origin": "https://h5forphone.wostore.cn", "Content-Type": "application/json"}
            json_data = json.dumps(body1, separators=(',', ':'), ensure_ascii=True)
            res1 = self.session.post(url1, data=json_data, headers=headers1, timeout=15).json()
            if str(res1.get("code")) != "0":
                msg = res1.get("msg", str(res1))
                self.log(f"沃云手机: 登录第一步失败 - {msg}")
                return None
            redirect_url = res1.get("data", {}).get("url", "")
            match = re.search(r'token=([^&]+)', redirect_url)
            if not match:
                if "protocol" in redirect_url or "sign" in redirect_url:
                    self.log("沃云手机: 未开通业务 (检测到协议签署跳转)，跳过")
                else:
                    self.log(f"沃云手机: 无法提取 Token, 跳转URL: {redirect_url}")
                return None
            first_token = match.group(1)
            time.sleep(1)
            url2 = "https://uphone.wostore.cn/h5api/activity-service/user/login"
            body2 = {
                "identityType": "cloudPhoneLogin", "code": first_token, "channelId": "ST-Zujian001-gs",
                "activityId": "Lottery_251201", "device": "device"
            }
            headers2 = {"Origin": "https://uphone.wostore.cn", "X-USR-TOKEN": first_token}
            res2 = self.session.post(url2, json=body2, headers=headers2, timeout=15).json()
            if str(res2.get("code")) == "200":
                user_token = res2.get("data", {}).get("user_token")
                return {"firstToken": first_token, "user_token": user_token}
            else:
                self.log(f"沃云手机: 登录第二步失败 - {res2.get('msg', str(res2))}")
                return None
        except Exception as e:
            self.log(f"沃云手机: 登录异常 {e}")
            return None

    def wostore_cloud_sign(self, user_token):
        try:
            url = "https://uphone.wostore.cn/h5api/activity-service/points/v1/sign"
            body = {"activityCode": "Points_Sign_2507"}
            headers = {"X-USR-TOKEN": user_token, "Origin": "https://uphone.wostore.cn"}
            res = self.session.post(url, json=body, headers=headers).json()
            if res.get("code") == 200:
                self.log("沃云手机: 积分签到成功", notify=True)
            else:
                pass # Fail silently or log if needed context
        except Exception:
            pass

    def wostore_cloud_task_list(self, user_token):
        try:
            url = "https://uphone.wostore.cn/h5api/activity-service/user/task/list"
            body = {"activityCode": "Lottery_251201"}
            headers = {"X-USR-TOKEN": user_token}
            self.session.post(url, json=body, headers=headers)
        except Exception:
            pass

    def wostore_cloud_get_chance(self, user_token, task_code):
        try:
            url = "https://uphone.wostore.cn/h5api/activity-service/user/task/raffle/get"
            body = {"activityCode": "Lottery_251201", "taskCode": task_code}
            headers = {"X-USR-TOKEN": user_token}
            self.session.post(url, json=body, headers=headers)
        except Exception:
            pass

    def wostore_cloud_draw(self, user_token):
        try:
            url = "https://uphone.wostore.cn/h5api/activity-service/lottery"
            body = {"activityCode": "Lottery_251201"}
            headers = {"X-USR-TOKEN": user_token}
            res = self.session.post(url, json=body, headers=headers).json()
            if res.get("code") == 200:
                prize = res.get("data", {}).get("prizeName", "未中奖")
                self.log(f"沃云手机: 抽奖结果 - {prize}", notify=True)
            else:
                self.log(f"沃云手机: 抽奖失败 - {res.get('msg', str(res))}")
        except Exception as e:
            self.log(f"沃云手机: 抽奖异常 {e}")

    def wostore_cloud_task(self, is_query_only=False):
        self.log("==== 沃云手机 ====")
        if is_query_only:
             self.log("沃云手机: [查询模式] 此平台暂无资产或余额可供查询", notify=True)
             return
        target_url = "https://h5forphone.wostore.cn/cloudPhone/dialogCloudPhone.html?channel_id=ST-Zujian001-gs&cp_id=91002997"
        ticket_res = self.openPlatLineNew(target_url)
        if not ticket_res:
            self.log("沃云手机: 获取入口 Ticket 失败")
            return
        ticket = ticket_res
        if isinstance(ticket, dict):
            ticket = ticket.get('ticket')
        if not ticket:
             self.log("沃云手机: 获取入口 Ticket 失败 (为空)")
             return
        tokens = self.wostore_cloud_login(ticket)
        if not tokens:
            self.log("沃云手机: 登录失败，跳过后续任务")
            return
        user_token = tokens['user_token']
        self.wostore_cloud_sign(user_token)
        time.sleep(2)
        self.wostore_cloud_task_list(user_token)
        time.sleep(1)
        self.wostore_cloud_get_chance(user_token, "2508-01")
        time.sleep(2)
        self.wostore_cloud_draw(user_token)

    def regional_task(self, is_query_only=False):
        """区域专区任务入口"""
        is_xinjiang = False
        is_henan = False
        if hasattr(self, 'city_info') and self.city_info and isinstance(self.city_info, list):
            try:
                for city in self.city_info:
                    pro_name = city.get('proName', '')
                    if "新疆" in pro_name: is_xinjiang = True
                    if "河南" in pro_name: is_henan = True
            except: pass
        if is_query_only:
            self.log("==== 区域专区 (查询模式) ====")
            if is_xinjiang:
                self.log("新疆专区: [查询模式] 跳过每日打卡 (无查询接口)")
            if is_henan:
                is_signed = self.shangdu_get_sign_status()
                if is_signed is True:
                    self.log("河南商都: [状态查询] 今日已签到")
                elif is_signed is False:
                    self.log("河南商都: [状态查询] 今日未签到")
                else:
                    self.log("河南商都: [状态查询] 查询失败")
            return
        if is_xinjiang:
            self.log("==== 新疆专区 ====")
            self.xj_task_main()
        if is_henan:
            self.log("==== 河南商都 ====")
            self.shangdu_task_main()

    def xj_task_main(self):
        ticket = self.openPlatLineNew("https://zy100.xj169.com/touchpoint/openapi/jumpHandRoom1G?source=155&type=02")
        if not ticket:
            return
        token = self.xj_get_token(ticket)
        if token:
            self.xj_do_draw(token, "Jan2026Act")
            day = datetime.now().day
            if 19 <= day <= 25:
                self.xj_usersday_task(token)

    def xj_get_token(self, ticket):
        try:
            url = "https://zy100.xj169.com/touchpoint/openapi/getTokenAndCity"
            data = {"ticket": ticket}
            headers = {"Referer": f"https://zy100.xj169.com/touchpoint/openapi/jumpHandRoom1G?source=155&type=02&ticket={ticket}"}
            res = self.session.post(url, data=data, headers=headers).json()
            if res.get('result', {}).get('code') == 0:
                return res.get('result', {}).get('data', {}).get('token')
            return None
        except: return None

    def xj_do_draw(self, token, act_id):
        try:
            url = f"https://zy100.xj169.com/touchpoint/openapi/marchAct/draw_{act_id}"
            data = {"activityId": f"daka{act_id}", "prizeId": ""}
            headers = {"userToken": token}
            res = self.session.post(url, data=data, headers=headers).json()
            msg = res.get('result', {}).get('msg') or res.get('result', {}).get('data') or "失败"
            self.log(f"新疆专区: 每日打卡 - {msg}", notify=True)
        except Exception as e:
            self.log(f"新疆专区: 打卡异常 {e}")

    def xj_usersday_task(self, token):
        try:
            url = "https://zy100.xj169.com/touchpoint/openapi/marchAct/draw_UsersDay2025Act"
            data = {"activityId": "usersDay2025Act", "prizeId": "hfq_twenty"}
            headers = {"userToken": token}
            res = self.session.post(url, data=data, headers=headers).json()
            msg = res.get('result', {}).get('msg') or res.get('result', {}).get('data') or "失败"
            self.log(f"新疆客户日: 秒杀结果 - {msg}", notify=True)
        except: pass

    def shangdu_get_sign_status(self):
        try:
            url = "https://app.shangdu.com/monthlyBenefit/v1/signIn/queryCumulativeSignAxis"
            headers = {
                "Origin": "https://app.shangdu.com",
                "Referer": "https://app.shangdu.com/monthlyBenefit/index.html",
                "edop_flag": "0", "Content-Type": "application/json"
            }
            res = self.session.post(url, json={}, headers=headers).json()
            if res.get('result', {}).get('code') == "0000":
                return res.get('result', {}).get('data', {}).get('todaySignFlag') == "1"
            return None
        except: return None

    def shangdu_sign_retry(self):
        try:
            url = "https://app.shangdu.com/monthlyBenefit/v1/signIn/userSignIn"
            headers = {
                "Origin": "https://app.shangdu.com",
                "Referer": "https://app.shangdu.com/monthlyBenefit/index.html",
                "edop_flag": "0", "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/json"
            }
            res = self.session.post(url, json={}, headers=headers).json()
            code = res.get('result', {}).get('code')
            data = res.get('result', {}).get('data', {})
            if code == "0000":
                prize = data.get('prizeResp', {}).get('prizeName')
                if prize: self.log(f"河南商都: 签到成功(重试) - 获得 {prize}", notify=True)
                else: self.log("河南商都: 签到成功(重试)")
            elif code == "0019":
                self.log("河南商都: 重试仍返回重复签到")
            else:
                self.log(f"河南商都: A签到重试失败 - {res.get('result', {}).get('msg')}")
        except Exception as e:
            self.log(f"河南商都: 签到重试异常 {e}")

    def shangdu_task_main(self):
        if not self.ecs_token: return
        url = f"https://m.client.10010.com/edop_ng/getTicketByNative?appId=edop_unicom_4b80047a&token={self.ecs_token}"
        res = self.session.get(url).json()
        ticket = res.get('result', {}).get('ticket')
        if not ticket:
            self.log("河南商都: 获取Ticket失败")
            return
        login_url = f"https://app.shangdu.com/monthlyBenefit/v1/common/config?ticket={ticket}"
        headers_login = {
             "Origin": "https://app.shangdu.com",
             "Referer": "https://app.shangdu.com/monthlyBenefit/index.html",
             "edop_flag": "0", "Accept": "application/json, text/plain, */*"
        }
        self.session.get(login_url, headers=headers_login)
        time.sleep(1.5)
        sign_url = "https://app.shangdu.com/monthlyBenefit/v1/signIn/userSignIn"
        headers_sign = {
             "Origin": "https://app.shangdu.com",
             "Referer": "https://app.shangdu.com/monthlyBenefit/index.html",
             "edop_flag": "0", "X-Requested-With": "XMLHttpRequest",
             "Content-Type": "application/json"
        }
        res_sign = self.session.post(sign_url, json={}, headers=headers_sign).json()
        code = res_sign.get('result', {}).get('code')
        data = res_sign.get('result', {}).get('data', {})
        if code == "0000":
             if data.get('value') == "0001":
                 self.log("河南商都: 签到失败 - Cookie无效")
             else:
                 prize = data.get('prizeResp', {}).get('prizeName', '已签到')
                 self.log(f"河南商都: 签到结果 - {prize}", notify=True)
        elif code == "0019":
             time.sleep(1)
             is_signed = self.shangdu_get_sign_status()
             if is_signed is True:
                 self.log("河南商都: 今日已签到")
             elif is_signed is False:
                 self.log("河南商都: 状态未签到但返回重复，尝试重试...")
                 time.sleep(2)
                 self.shangdu_sign_retry()
             else:
                 self.log("河南商都: 今日已签到 (状态未知)")
        else:
             self.log(f"河南商都: 签到失败 - {code} : {res_sign.get('result', {}).get('msg')}")

    def woread_encrypt(self, data):
        try:
            key = b'woreadst^&*12345'
            iv = b'16-Bytes--String'
            cipher = AES.new(key, AES.MODE_CBC, iv)
            if isinstance(data, dict):
                data_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
            else:
                data_str = str(data)
            pad_len = 16 - (len(data_str.encode('utf-8')) % 16)
            data_str = data_str + chr(pad_len) * pad_len
            ciphertext = cipher.encrypt(data_str.encode('utf-8'))
            hex_str = ciphertext.hex()
            return base64.b64encode(hex_str.encode('utf-8')).decode('utf-8')
        except Exception as e:
            self.log(f"woread_encrypt error: {e}")
            return ""

    def woread_auth(self):
        try:
            product_id = "10000002"
            secret_key = "7k1HcDL8RKvc"
            timestamp = str(round(time.time() * 1000))
            sign_str = f"{product_id}{secret_key}{timestamp}"
            md5_hash = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
            date_str = datetime.now().strftime('%Y%m%d%H%M%S')
            crypt_text_obj = {"timestamp": date_str}
            encoded_sign = self.woread_encrypt(crypt_text_obj)
            url = f"https://10010.woread.com.cn/ng_woread_service/rest/app/auth/{product_id}/{timestamp}/{md5_hash}"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": COMMON_CONSTANTS['UA'],
            }
            res = self.session.post(url, json={"sign": encoded_sign}, headers=headers).json()
            if res.get('code') == "0000":
                self.woread_accesstoken = res.get('data', {}).get('accesstoken')
                return True
            else:
                self.log(f"阅读专区认证失败: {res.get('message')}")
                return False
        except Exception as e:
            self.log(f"woread_auth error: {e}")
            return False

    def woread_login(self):
        try:
            if not hasattr(self, 'woread_accesstoken') or not self.woread_accesstoken:
                if not self.woread_auth():
                    return False
            if not self.token_online:
                self.log("阅读专区: 缺少 token_online，无法登录")
                return False
            token_enc = self.woread_encrypt(self.token_online)
            phone_str = self.account_mobile if self.account_mobile else "13800000000"
            phone_enc = self.woread_encrypt(phone_str)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            inner_json = json.dumps({
                "tokenOnline": token_enc,
                "phone": phone_enc,
                "timestamp": timestamp
            }, separators=(',', ':'), ensure_ascii=False)
            encoded_sign = self.woread_encrypt(inner_json)
            url = "https://10010.woread.com.cn/ng_woread_service/rest/account/login"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": COMMON_CONSTANTS['UA'],
            }
            if hasattr(self, 'woread_accesstoken') and self.woread_accesstoken:
                headers["accesstoken"] = self.woread_accesstoken
            res = self.session.post(url, json={"sign": encoded_sign}, headers=headers, timeout=15).json()
            if res.get('code') == "0000":
                data = res.get('data', {})
                self.woread_token = data.get('token')
                self.woread_userid = data.get('userid')
                self.woread_userindex = data.get('userindex')
                self.woread_verifycode = data.get('verifycode')
                if data.get('phone'):
                    self.mobile = data['phone']
                self.log("阅读专区: 登录成功")
                return True
            else:
                self.log(f"阅读专区登录失败: {res.get('message')}")
                return False
        except Exception as e:
            self.log(f"woread_login error: {e}")
            return False

    def woread_queryTicketAccount(self):
        try:
            if not hasattr(self, 'woread_token') or not self.woread_token:
                if not self.woread_login():
                     return
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            params = {
                "timestamp": timestamp,
                "phone": self.mobile if self.mobile else "",
                "token": self.woread_token
            }
            sign = self.woread_encrypt(params)
            url = "https://10010.woread.com.cn/ng_woread_service/rest/phone/vouchers/queryTicketAccount"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": COMMON_CONSTANTS['UA'],
            }
            if hasattr(self, 'woread_accesstoken') and self.woread_accesstoken:
                headers["accesstoken"] = self.woread_accesstoken
            res = self.session.post(url, json={"sign": sign}, headers=headers).json()
            if res.get('code') == "0000":
                data = res.get('data', {})
                usable_num = int(data.get('usableNum', 0))
                balance_yuan = "{:.2f}".format(usable_num / 100)
                self.log(f"💰 [资产-阅读红包] 余额: {balance_yuan}元", notify=True)
            else:
                self.log(f"阅读红包查询失败: {res.get('message')}")
        except Exception as e:
            self.log(f"woread_queryTicketAccount error: {e}")

    def woread_get_book_info(self):
        try:
            url1 = "https://10010.woread.com.cn/ng_woread_service/rest/basics/recommposdetail/14856"
            headers = {
                "User-Agent": COMMON_CONSTANTS['UA'],
                "accesstoken": self.woread_accesstoken
            }
            res1 = self.session.get(url1, headers=headers)
            try:
                res1 = res1.json()
            except:
                self.log(f"阅读专区: 获取书架响应非JSON: {res1.text[:100]}")
                return False
            if res1.get('code') == '0000':
                msg_list = res1.get('data', {}).get('booklist', {}).get('message', [])
                if msg_list:
                    self.wr_catid = msg_list[0].get('catindex')
                    self.wr_cntindex = msg_list[0].get('cntindex')
                bind_info = res1.get('data', {}).get('bindinfo', [])
                if bind_info:
                    self.wr_cardid = bind_info[0].get('recommposiindex')
            else:
                self.log("阅读专区: 获取书架失败")
                return False
            if not getattr(self, 'wr_cntindex', None): return False
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            param = {
                "curPage": 1, "limit": 30, "index": self.wr_cntindex, "sort": 0, "finishFlag": 1,
                "timestamp": timestamp,
                "phone": self.mobile if self.mobile else "",
                "token": getattr(self, 'woread_token', ''),
                "userid": getattr(self, 'woread_userid', ''),
                "userId": getattr(self, 'woread_userid', ''),
                "userIndex": getattr(self, 'woread_userindex', ''),
                "verifyCode": getattr(self, 'woread_verifycode', '')
            }
            sign = self.woread_encrypt(param)
            url2 = "https://10010.woread.com.cn/ng_woread_service/rest/cnt/chalist"
            res2_raw = self.session.post(url2, json={"sign": sign}, headers=headers)
            try:
                res2 = res2_raw.json()
            except:
                self.log(f"阅读专区: 获取章节响应非JSON: {res2_raw.text[:100]}")
                return False
            lst = res2.get('list', []) or res2.get('data', {}).get('list', [])
            if lst:
                content = lst[0].get('charptercontent', [])
                if content:
                    self.wr_chapterallindex = content[0].get('chapterallindex')
                    self.wr_chapterid = content[0].get('chapterid')
                    return True
            return False
        except Exception as e:
            self.log(f"阅读专区: 获取书籍信息异常: {e}")
            return False

    def woread_read_process(self):
        if not self.woread_get_book_info():
            self.log("阅读专区: 无法获取书籍信息，跳过阅读")
            return
        headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301}",
                "accesstoken": self.woread_accesstoken
        }
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        phone = self.mobile if self.mobile else ""
        token = getattr(self, 'woread_token', '')
        userid = getattr(self, 'woread_userid', '')
        userindex = getattr(self, 'woread_userindex', '')
        verifycode = getattr(self, 'woread_verifycode', '')
        common_params = {
            "timestamp": timestamp,
            "phone": phone,
            "token": token,
            "userid": userid,
            "userId": userid,
            "userIndex": userindex,
            "userAccount": phone,
            "verifyCode": verifycode
        }
        param = {
          "chapterAllIndex": self.wr_chapterallindex,
          "cntIndex": self.wr_cntindex,
          "cntTypeFlag": "1",
          **common_params
        }
        sign = self.woread_encrypt(param)
        hb_url = f"https://10010.woread.com.cn/ng_woread_service/rest/cnt/wordsDetail?catid={self.wr_catid}&cardid={self.wr_cardid}&cntindex={self.wr_cntindex}&chapterallindex={self.wr_chapterallindex}&chapterseno=1"
        self.session.post(hb_url, json={"sign": sign}, headers=headers)
        add_param = {
          "readTime": "2",
          "cntIndex": self.wr_cntindex,
          "cntType": "1",
          "catid": "0",
          "pageIndex": "",
          "cardid": self.wr_cardid,
          "cntindex": self.wr_cntindex,
          "cnttype": "1",
          "chapterallindex": self.wr_chapterallindex,
          "chapterseno": "1",
          "channelid": "",
          "chapterid": self.wr_chapterid,
          "readtype": 1,
          "isend": "0",
          **common_params
        }
        add_sign = self.woread_encrypt(add_param)
        add_url = "https://10010.woread.com.cn/ng_woread_service/rest/history/addReadTime"
        res = self.session.post(add_url, json={"sign": add_sign}, headers=headers).json()
        res_code = str(res.get('code', ''))
        res_msg = str(res.get('message', ''))
        if res_code == '0000':
            self.log("阅读专区: 模拟阅读成功")
        elif res_code == '9999' or '9999' in res_msg or '不存在阅读记录' in res_msg:
            # addReadTime 返回9999不影响实际阅读结果
            self.log("阅读专区: 模拟阅读成功（阅读记录已提交）")
        else:
             self.log(f"阅读专区: 模拟阅读失败: {res_msg or res}")



    def woread_draw_new(self):
        try:
             headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 unicom{version:iphone_c@12.0301}",
                "accesstoken": self.woread_accesstoken
             }
             timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
             param = {
                "activeindex": "8051",
                "timestamp": timestamp, "phone": self.mobile if self.mobile else "", "token": self.woread_token
             }
             sign = self.woread_encrypt(param)
             url = "https://10010.woread.com.cn/ng_woread_service/rest/basics/doDraw"
             res = self.session.post(url, json={"sign": sign}, headers=headers).json()
             if res.get('code') == '0000':
                 prize = res.get('data', {}).get('prizedesc')
                 if prize:
                     self.log(f"阅读专区: 抽奖成功: {prize}", notify=True)
                 else:
                     self.log("阅读专区: 抽奖完成 (未中奖)")
             else:
                 self.log(f"阅读专区: 抽奖失败: {res.get('message')}")
        except Exception as e:
            self.log(f"woread_draw_new error: {e}")

    def woread_task(self):
        self.log("==== 联通阅读 ====")
        if not self.woread_login():
             self.log("阅读专区: 登录失败，跳过任务")
             return
        self.woread_queryTicketAccount()
        self.woread_read_process()
        time.sleep(3)
        self.woread_draw_new()

    def query_market_raffle_records(self, user_token):
        self.log("权益超市: 正在查询抽奖记录...")
        try:
            url = "https://backward.bol.wo.cn/prod-api/market/contactReceive/queryReceiveRecord"
            headers = {
                "Authorization": f"Bearer {user_token}",
                "User-Agent": COMMON_CONSTANTS["MARKET_UA"],
                "Origin": "https://contact.bol.wo.cn",
                "Referer": "https://contact.bol.wo.cn/"
            }
            mobile = getattr(self, "account_mobile", getattr(self, "mobile", ""))
            payload = {
                "isReceive": None,
                "receiveStatus": None,
                "limit": 20,
                "page": 1,
                "mobile": mobile,
                "businessSources": ["3", "4", "5", "6", "99"],
                "isPromotion": 1,
                "returnFormatType": 1
            }
            res = self.session.post(url, json=payload, headers=headers).json()
            if res.get('code') == 200:
                records = res.get('data', {}).get('recordObjs', [])
                if records:
                    display_records = records[:10]
                    self.log(f"权益超市: 最近 {len(display_records)} 条抽奖记录:", notify=True)
                    for item in display_records:
                        self.log(f"    - [{item.get('receiveTime')}] {item.get('recordName')}", notify=True)
                else:
                    self.log("权益超市: 无近期抽奖记录。")
            else:
                self.log(f"权益超市: 查询抽奖记录失败: {res.get('msg')}")
        except Exception as e:
            self.log(f"query_market_raffle_records error: {e}")

    def query_phone_recharge_records(self, user_token):
        self.log("权益超市: 正在查询本月话费抢购记录...")
        try:
            url = "https://backward.bol.wo.cn/prod-api/market/contactReceive/queryReceiveRecord"
            headers = {
                "Authorization": f"Bearer {user_token}",
                "User-Agent": COMMON_CONSTANTS["MARKET_UA"],
                "Origin": "https://contact.bol.wo.cn",
                "Referer": "https://contact.bol.wo.cn/"
            }
            mobile = getattr(self, "account_mobile", getattr(self, "mobile", ""))
            payload = {
                "isReceive": None,
                "receiveStatus": None,
                "limit": 50,
                "page": 1,
                "mobile": mobile,
                "businessSources": ["3", "4", "5", "6", "99"],
                "isPromotion": 1,
                "returnFormatType": 1
            }
            res = self.session.post(url, json=payload, headers=headers).json()
            if res.get('code') == 200:
                records = res.get('data', {}).get('recordObjs', [])
                total_amount = 0.0
                current_month = datetime.now().strftime('%Y-%m')
                count = 0
                for item in records:
                    create_time = item.get('receiveTime', '')
                    name = item.get('recordName', '')
                    if current_month in create_time and any(k in name for k in ['话费', '充值', '红包']):
                        match = re.search(r'(\d+(\.\d+)?)元', name)
                        if match:
                            amount = float(match.group(1))
                            total_amount += amount
                            count += 1
                if count > 0:
                     self.log(f"💰 [资产-抢购] 本月权益超市话费累计: {total_amount:.2f}元", notify=True)
                else:
                     self.log("权益超市: 本月暂无话费抢购记录")
            else:
                self.log(f"权益超市: 查询话费记录失败: {res.get('msg')}")
        except Exception as e:
            self.log(f"query_phone_recharge_records error: {e}")

    def sign_query_my_prizes(self):
        self.log("正在查询账户明细 (抢兑)...")
        try:
            url = "https://act.10010.com/SigninApp/convert/phoneDetails"
            form = {
                "log_type": "1",
                "number": "1",
                "list_num": ""
            }
            headers = {"Origin": "https://img.client.10010.com"}
            res = self.request("post", url, data=form, headers=headers)
            if not res: return
            result = res.json()
            if result.get('status') == '0000':
                data = result.get('data', {}).get('detailedBO', [])
                if data and isinstance(data, list):
                     logged_count = 0
                     for item in data:
                         if logged_count >= 5: break
                         remark = item.get('remark', '')
                         buss_name = item.get('from_bussname', '')
                         if "兑换" in remark or "兑换" in buss_name:
                             if logged_count == 0:
                                 self.log(f"📋 [账户明细] 最近 5 条记录:", notify=True)
                             order_time = item.get('order_time', '')
                             amount = item.get('booksNumber') or item.get('books_number') or "0"
                             self.log(f"   🎁 [抢兑] {order_time} | {remark} (变动:{amount})", notify=True)
                             logged_count += 1
                     if logged_count == 0:
                         self.log("[账户明细] 暂无兑换记录")
                else:
                    self.log("[账户明细] 暂无兑换记录")
            else:
                self.log(f"[账户明细] 查询异常: {result.get('msg', 'Result Error')}")
        except Exception as e:
            self.log(f"sign_query_my_prizes error: {e}")

    def sign_task_main(self):
        self.log("==== 签到区 ====")
        self.sign_getTelephone(is_initial=True)
        self.sign_getContinuous(is_query_only=False)
        self.sign_getTaskList()
        sc = globalConfig.get("sign_config", {})
        if sc.get("run_grab_coupon", False):
            self.sign_grabCoupon()
        else:
            self.log("签到区-抢话费券: ⏭️ 已被子开关关闭，跳过")
        self.sign_getTelephone()
        self.sign_query_my_prizes()

    def execute_daily_tasks(self, query_only=False):
        if query_only:
            self.log("📋 [查询模式] 仅查询资产，跳过任务执行", notify=True)
            try:
                self.queryRemain()
                if globalConfig.get("enable_sign", True):
                    try:
                        self.sign_getContinuous(is_query_only=True)
                        self.sign_getTelephone()
                    except Exception as e:
                        self.log(f"首页签到查询异常: {e}")
                    try:
                        self.sign_query_my_prizes()
                    except Exception as e:
                        self.log(f"抢兑记录查询异常: {e}")
                if globalConfig.get("enable_ttlxj", True):
                    try:
                        self.ttlxj_task(is_query_only=True)
                    except Exception as e:
                        self.log(f"天天领现金查询异常: {e}")
                if globalConfig.get("enable_market", True):
                    try:
                        self.market_task(is_query_only=True)
                    except Exception as e:
                        self.log(f"权益超市查询异常: {e}")
                if globalConfig.get("enable_woread", True):
                    try:
                        self.woread_queryTicketAccount()
                    except Exception as e:
                        self.log(f"联通阅读查询异常: {e}")
                if globalConfig.get("enable_aiting", True):
                    try:
                        self.aiting_task(is_query_only=True)
                    except Exception as e:
                        self.log(f"联通爱听查询异常: {e}")
                if globalConfig.get("enable_security", True):
                    try:
                        self.securityButlerTask(is_query_only=True)
                    except Exception as e:
                        self.log(f"安全管家查询异常: {e}")
                if globalConfig.get("enable_ltyp", True):
                    try:
                        self.ltyp_task(is_query_only=True)
                    except Exception as e:
                        self.log(f"联通云盘查询异常: {e}")
                if globalConfig.get("enable_wostore", True):
                    try:
                        self.wostore_cloud_task(is_query_only=True)
                    except Exception as e:
                        self.log(f"沃云手机查询异常: {e}")
                if globalConfig.get("enable_regional", True):
                    try:
                        self.regional_task(is_query_only=True)
                    except Exception as e:
                        pass
            except Exception as e:
                self.log(f"查询异常: {e}")
            return
        if globalConfig.get("enable_sign", True):
            self.sign_task_main()
        else:
            self.log("==== 签到区 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_ltzf", True):
            self.ltzf_task()
        else:
            self.log("==== 联通祝福 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_ttlxj", True):
            self.ttlxj_task()
        else:
            self.log("==== 天天领现金 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_market", True):
            self.market_task()
        else:
            self.log("==== 权益超市 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_woread", True):
            self.woread_task()
        else:
            self.log("==== 联通阅读 ==== ⏭️ 已被总开关关闭，跳过")
        need_cooldown = globalConfig.get("enable_woread", True) and globalConfig.get("enable_aiting", True)
        if need_cooldown:
            self.log("⏳ 等待120秒（阅读冷却：联通限制两次阅读间隔2分钟）...")
            time.sleep(120)
        if globalConfig.get("enable_aiting", True):
            self.aiting_task()
        else:
            self.log("==== 联通爱听 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_security", True):
            self.securityButlerTask()
        else:
            self.log("==== 安全管家 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_ltyp", True):
            self.ltyp_task()
        else:
            self.log("==== 联通云盘 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_wostore", True):
            self.wostore_cloud_task()
        else:
            self.log("==== 沃云手机 ==== ⏭️ 已被总开关关闭，跳过")
        if globalConfig.get("enable_regional", True):
            self.regional_task()
        else:
            self.log("==== 区域专区 ==== ⏭️ 已被总开关关闭，跳过")

def do_notify(users):
    notify_content = []
    for u in users:
        if u.notify_logs:
            phone = u.mobile or u.account_mobile
            phone_str = mask_str(phone) if phone else ""
            notify_content.append(f"【账号{u.index}】{phone_str}")
            notify_content.extend(u.notify_logs)
            notify_content.append("")
    if notify_content:
        content = "\n".join(notify_content)
        try:
            from notify import send
            send("中国联通", content)
            print(f"推送成功 (内容长度: {len(content)})")
        except Exception as e:
            print(f"推送失败，可能未配置 notify.py: {str(e)}")
    else:
        print("无推送内容")

def main():
    global GRAB_AMOUNT
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [Script Start] chinaUnicom Python v1.0.2")
    cookies = os.environ.get("chinaUnicomCookie", "")
    if not cookies:
        print("[-] 未在环境变量 chinaUnicomCookie 中找到配置")
        sys.exit(1)
    accounts = [c for c in re.split(r'[&\n]', cookies) if c.strip()]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 发现 {len(accounts)} 个账号")
    print("")
    users = []
    for idx, config in enumerate(accounts):
        u = UserService(idx + 1, config.strip())
        users.append(u)
        if u.appId:
             print(f"账号[{idx+1}] 识别到 Token#AppId 模式，使用自定义AppId: {u.appId}")
        elif u.account_mobile:
             print(f"账号[{idx+1}] 识别到账号密码模式: {mask_str(u.account_mobile)}")
        try:
            if u.token_online:
                u.get_city_info()
        except: pass
    print(f"共找到{len(accounts)}个账号")
    print("")
    env_amount = os.environ.get("UNICOM_GRAB_AMOUNT", "")
    if env_amount and env_amount.isdigit():
        GRAB_AMOUNT = int(env_amount)
    query_only = os.environ.get("UNICOM_TEST_MODE", "").strip().lower() == "query"
    if query_only:
        print("[Test Mode] 仅查询模式，跳过任务执行")
    # 抢兑模式检测 (在打印前判断)
    sc = globalConfig.get("sign_config", {})
    mc = globalConfig.get("market_config", {})
    grab_mode = False
    if sc.get("run_grab_coupon", False) and globalConfig.get("enable_sign", True) and not query_only:
        hour = datetime.now().hour
        current_min = datetime.now().minute
        if hour in [9, 17] and (58 <= current_min <= 59):
            grab_mode = True
    print("-" * 36)
    # 打印各模块开关状态
    switch_map = [
        ("enable_sign",     "首页签到"),
        ("enable_ltzf",     "联通祝福"),
        ("enable_ttlxj",    "天天领现金"),
        ("enable_market",   "权益超市"),
        ("enable_woread",   "联通阅读"),
        ("enable_aiting",   "联通爱听"),
        ("enable_security", "安全管家"),
        ("enable_ltyp",     "联通云盘"),
        ("enable_wostore",  "沃云手机"),
        ("enable_regional", "区域专区"),
    ]
    for key, label in switch_map:
        enabled = globalConfig.get(key, True)
        if grab_mode:
            # 抢兑模式: 仅签到区(抢兑)运行, 其余全部跳过
            if key == "enable_sign":
                status = "运行(仅抢兑)"
            else:
                status = "跳过(抢兑模式)"
        elif query_only:
            status = "仅查询" if enabled else "关闭"
        else:
            status = "运行" if enabled else "关闭"
        print(f"{label}设置为: {status}")
        # 签到区后面紧跟子开关
        if key == "enable_sign" and enabled and not query_only:
            print(f"  └─ 抢话费券: {'开启' if sc.get('run_grab_coupon', False) else '关闭'}")
        # 权益超市后面紧跟子开关 (抢兑模式下不打印, 因为整个权益超市都跳过)
        if key == "enable_market" and enabled and not query_only and not grab_mode:
            print(f"  └─ 浇水: {'开启' if mc.get('run_water', True) else '关闭'}")
            print(f"  └─ 做任务: {'开启' if mc.get('run_task', True) else '关闭'}")
            print(f"  └─ 抽奖: {'开启' if mc.get('run_draw', True) else '关闭'}")
            print(f"  └─ 自动领奖: {'开启' if mc.get('run_claim', False) else '关闭'}")
    print(f"设备ID刷新: {'强制刷新' if globalConfig.get('refresh_device_id', False) else '使用缓存'}")
    print("-" * 36)
    print("")
    # --- 定时抢兑模式: 仅并发执行抢话费券, 完成后直接退出 ---
    if grab_mode:
        hour = datetime.now().hour
        current_min = datetime.now().minute
        print(f"⏰ [自动触发] 检测到抢兑时间点 ({hour}:{current_min:02d})，进入并发抢兑模式")
        print(f"🚨🚨🚨 [抢兑模式已启动] 目标: {GRAB_AMOUNT}元话费券 🚨🚨🚨")
        print("")
        from concurrent.futures import ThreadPoolExecutor

        def run_grab_task(u):
            u.configure_proxy()
            if not u.token_online and u.account_mobile:
                u.load_token_from_cache()
            is_valid = u.onLine()
            if not is_valid and u.account_mobile and u.account_password:
                u.unicom_login()
                is_valid = u.onLine()
            if is_valid:
                u.save_token_to_cache()
                u.sign_grabCoupon()
            else:
                u.log("登录流程失败，跳过该账号")

        print(f"🚀 [并发模式] 启动 {len(accounts)} 个账号同时抢兑...")
        with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
            futures = [executor.submit(run_grab_task, u) for u in users]
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    print(f"[-] Thread Error: {e}")
        do_notify(users)
        return
    print("🚀 开始串行执行日常任务...")
    print("")
    for u in users:
        print("")
        print(f"🔄 正在初始化账号[{u.index}]...")
        u.configure_proxy()
        if not u.token_online and u.account_mobile:
            u.load_token_from_cache()
        if not u.token_online and u.account_mobile and u.account_password:
             u.unicom_login()
        if u.onLine():
             u.save_token_to_cache()
             print("")
             print(f"------------------ 账号[{u.index}][{mask_str(u.account_mobile)}] ------------------")
             print("")
             u.execute_daily_tasks(query_only=query_only)
             print("⏳ 账号处理完毕，等待 2 秒...")
             time.sleep(2)
        else:
             u.log("登录流程失败，跳过该账号")
    do_notify(users)
if __name__ == "__main__":
    main()
