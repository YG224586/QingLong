#鼎鸿保龄观澜球馆微信小程序
#变量名：Glqg
#变量值：Authorization
#在环境变量和依赖无错的情况下，如果脚本运行出错，尝试修改46行的venueId值
#by：重庆第一深情

import os
import json
import requests
import logging
from notify import send

# 配置日志，加入表情符号使日志更美观
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 表情符号定义
EMOJI = {
    'info': 'ℹ️',
    'success': '✅',
    'warning': '⚠️',
    'error': '❌',
    'checkin': '📅',
    'user': '👤',
    'points': '💎',
    'start': '🚀',
    'end': '🏁'
}

# 获取环境变量
auth_token = os.getenv("Glqg")
if not auth_token:
    logger.error(f"{EMOJI['error']} 错误: 未设置Glqg环境变量")
    exit(1)

# 配置API地址
USER_INFO_URL = "https://smallroutine.dhbowling.com/app/index/user"
CHECKIN_URL = "https://smallroutine.dhbowling.com/app/signin/add"

# 请求参数
payload = {
    'venueId': "1392297544849584129"
}

# 请求头
headers = {
    'User-Agent': "Mozilla/5.0 (Linux; Android 15; PKG110 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380215 MMWEBSDK/20250804 MMWEBID/6169 MicroMessenger/8.0.63.2920(0x28003F32) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
    'Authorization': auth_token,
    'charset': "utf-8",
    'Referer': "https://servicewechat.com/wx95433e9c9351c8ff/22/page-frame.html",
}

def send_request(url, data, headers):
    """发送HTTP请求并返回解析后的JSON数据"""
    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()  # 抛出HTTP错误状态码
        return json.loads(response.text)
    except requests.exceptions.RequestException as e:
        logger.error(f"{EMOJI['error']} 请求失败: {str(e)}")
        return None
    except json.JSONDecodeError:
        logger.error(f"{EMOJI['error']} 解析响应JSON失败")
        return None

def main():
    # 执行签到
    logger.info(f"{EMOJI['start']} 开始执行签到流程...")
    logger.info(f"{EMOJI['checkin']} 正在提交签到请求...")
    
    checkin_result = send_request(CHECKIN_URL, payload, headers)
    
    if not checkin_result:
        send('鼎鸿保龄观澜球馆', f"{EMOJI['error']} 签到请求失败，无法获取签到状态")
        return
    
    # 获取签到状态信息
    checkin_message = checkin_result.get('message', '未知状态')
    logger.info(f"{EMOJI['checkin']} 签到状态: {checkin_message}")
    
    # 获取用户信息
    logger.info(f"{EMOJI['user']} 正在获取用户信息...")
    user_info = send_request(USER_INFO_URL, payload, headers)
    
    if not user_info:
        send('鼎鸿保龄观澜球馆', f"{EMOJI['checkin']} 签到状态：{checkin_message}\n{EMOJI['warning']} 获取用户信息失败")
        return
    
    # 解析用户信息
    data = user_info.get('data', {})
    nick_name = data.get('nickName', '未知用户')
    gold_sum = data.get('goldSum', '未知')
    
    logger.info(f"{EMOJI['user']} 用户: {nick_name}")
    logger.info(f"{EMOJI['points']} 总积分: {gold_sum}")
    
    # 发送通知
    notification_content = (f"{EMOJI['user']} 用户：{nick_name}\n"
                           f"{EMOJI['points']} 总积分：{gold_sum}\n"
                           f"{EMOJI['checkin']} 签到状态：{checkin_message}")
    send('鼎鸿保龄观澜球馆', notification_content)
    
    logger.info(f"{EMOJI['end']} 签到流程执行完毕")

if __name__ == "__main__":
    main()
    