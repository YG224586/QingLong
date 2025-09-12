#提醒：此脚本只适配插件提交或编码后的URL运行！
#提醒：此脚本只适配插件提交或编码后的URL运行！
#提醒：此脚本只适配插件提交或编码后的URL运行！

#【常规变量】
#账号变量名：sfsyUrl  （多号新建变量或者&）
#代理变量名：SF_PROXY_API_URL  （支持代理API或代理池）

#【采蜜活动相关变量】
#兑换区间设置：SFSY_DHJE  （例如 "23-15" 表示优先兑换23元，换不了就换20元，最后换15元，如果只兑换23元，填写“23”即可，其余额度请自行看活动页面）
#是否强制兑换：SFSY_DH  （填写 "true" 或 "false"  开启后 运行脚本则会进行兑换  关闭后 只有活动结束当天运行才进行兑换   默认为关闭状态）
#面额兑换次数：SFSY_DHCS  （默认为3次，相当于23的卷会尝试兑换3次）


import hashlib
import json
import os
import random
import time
from datetime import datetime, timedelta
from sys import exit
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from urllib.parse import unquote

# 禁用安全请求警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
EXCHANGE_RANGE = os.getenv('SFSY_DHJE', '23-15')  # 默认：23-15
FORCE_EXCHANGE = os.getenv('SFSY_DH', 'false').lower() == 'true'  # 默认：false
MAX_EXCHANGE_TIMES = int(os.getenv('SFSY_DHCS', '3'))  # 默认：3
PROXY_API_URL = os.getenv('SF_PROXY_API_URL', '')  # 从环境变量获取代理API地址
AVAILABLE_AMOUNTS = ['23元', '20元', '15元', '10元', '5元', '3元', '2元', '1元']

def parse_exchange_range(exchange_range):
    if '-' in exchange_range:
        try:
            start_val, end_val = exchange_range.split('-')
            start_val = int(start_val.strip())
            end_val = int(end_val.strip())
            
            target_amounts = []
            for amount in AVAILABLE_AMOUNTS:
                amount_val = int(amount.replace('元', ''))
                if end_val <= amount_val <= start_val:
                    target_amounts.append(amount)
            
            return target_amounts
        except:
            print(f"❌ 兑换区间配置错误: {exchange_range}")
            return ['23元']  # 默认返回23元
    else:
        if exchange_range.endswith('元'):
            return [exchange_range]
        else:
            return [f"{exchange_range}元"]

def get_proxy():
    try:
        if not PROXY_API_URL:
            print('⚠️ 未配置代理API地址，将不使用代理')
            return None
            
        response = requests.get(PROXY_API_URL, timeout=10)
        if response.status_code == 200:
            proxy_text = response.text.strip()
            if ':' in proxy_text:
                proxy = f'http://{proxy_text}'
                return {
                    'http': proxy,
                    'https': proxy
                }
        print(f'❌ 获取代理失败: {response.text}')
        return None
    except Exception as e:
        print(f'❌ 获取代理异常: {str(e)}')
        return None

send_msg = ''
one_msg = ''

def Log(cont=''):
    global send_msg, one_msg
    print(cont)
    if cont:
        one_msg += f'{cont}\n'
        send_msg += f'{cont}\n'

inviteId = ['']

class RUN:
    def __init__(self, info, index):
        global one_msg
        one_msg = ''
        split_info = info.split('@')
        url = split_info[0]
        len_split_info = len(split_info)
        last_info = split_info[len_split_info - 1]
        self.send_UID = None
        if len_split_info > 0 and "UID_" in last_info:
            self.send_UID = last_info
        self.index = index + 1

        self.proxy = get_proxy()
        if self.proxy:
            print(f"✅ 成功获取代理: {self.proxy['http']}")
        
        self.s = requests.session()
        self.s.verify = False
        if self.proxy:
            self.s.proxies = self.proxy
            
        self.headers = {
            'Host': 'mcs-mimp-web.sf-express.com',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090551) XWEB/6945 Flue',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'none',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'zh-CN,zh',
            'platform': 'MINI_PROGRAM',
        }
        
        self.login_res = self.login(url)
        self.all_logs = [] 
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.member_day_black = False
        self.member_day_red_packet_drew_today = False
        self.member_day_red_packet_map = {}
        self.max_level = 8
        self.packet_threshold = 1 << (self.max_level - 1)
        self.is_last_day = False
        self.auto_exchanged = False
        self.exchange_count = 0
        self.force_exchange = FORCE_EXCHANGE
        self.totalPoint = 0
        self.usableHoney = 0
        self.activityEndTime = ""
        self.target_amounts = parse_exchange_range(EXCHANGE_RANGE)

    def get_deviceId(self, characters='abcdef0123456789'):
        result = ''
        for char in 'xxxxxxxx-xxxx-xxxx':
            if char == 'x':
                result += random.choice(characters)
            elif char == 'X':
                result += random.choice(characters).upper()
            else:
                result += char
        return result

    def login(self, sfurl):
        try:
            decoded_url = unquote(sfurl)
            ress = self.s.get(decoded_url, headers=self.headers)
            self.user_id = self.s.cookies.get_dict().get('_login_user_id_', '')
            self.phone = self.s.cookies.get_dict().get('_login_mobile_', '')
            self.mobile = self.phone[:3] + "*" * 4 + self.phone[7:] if self.phone else ''
            
            if self.phone:
                Log(f'👤 账号{self.index}:【{self.mobile}】登陆成功')
                return True
            else:
                Log(f'❌ 账号{self.index}获取用户信息失败')
                return False
        except Exception as e:
            Log(f'❌ 登录异常: {str(e)}')
            return False

    def getSign(self):
        timestamp = str(int(round(time.time() * 1000)))
        token = 'wwesldfs29aniversaryvdld29'
        sysCode = 'MCS-MIMP-CORE'
        data = f'token={token}&timestamp={timestamp}&sysCode={sysCode}'
        signature = hashlib.md5(data.encode()).hexdigest()
        data = {
            'sysCode': sysCode,
            'timestamp': timestamp,
            'signature': signature
        }
        self.headers.update(data)
        return data

    def do_request(self, url, data={}, req_type='post', max_retries=3):
        self.getSign()
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if req_type.lower() == 'get':
                    response = self.s.get(url, headers=self.headers, timeout=30)
                elif req_type.lower() == 'post':
                    response = self.s.post(url, headers=self.headers, json=data, timeout=30)
                else:
                    raise ValueError('Invalid req_type: %s' % req_type)
                    
                response.raise_for_status()
                
                try:
                    res = response.json()
              