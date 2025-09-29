# 当前脚本来自于http://script.345yun.cn脚本库下载！
#!/usr/bin/env python3
"""
 作者:  加鲁鲁
 日期:  2025/9/13
 小程序:  绿袋环保旧衣服 (小程序://旧衣服回收/pITuyGvQixcFNsC) 
 功能:  签到、查询积分、提现（当积分>=100时）
 变量:  ly_wxid_data (微信id) 多个账号用换行分割 
 定时:  一天一次
 cron:  10 10 * * *
 更新日志：
 2025/9/13   V1.0    初始化脚本
"""
# #小程序://旧衣服回收/pITuyGvQixcFNsC 
# 请确保注册后再跑本子
# -*- coding: utf-8 -*-
import os
import requests
import json
from datetime import datetime
import time
from wex_get import wx_code_auth  # 确保此模块可用

# 常量定义
APPID = "wx55da7d089eab6cdb"
HOST = "www.lvdhb.com"
MULTI_ACCOUNT_SPLIT = ["\n", "@", "&"]  # 分隔符列表
BASE_HEADERS = {
    'Host': HOST,
    'Connection': 'keep-alive',
    'xweb_xhr': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090c37) XWEB/14185',
    'Content-Type': 'application/json',
    'Accept': '*/*',
    'Sec-Fetch-Site': 'cross-site',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Referer': f'https://servicewechat.com/{APPID}/139/page-frame.html',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh;q=0.9'
}

def load_wxids():
    """从环境变量加载wxid列表，支持多种分隔符"""
    wxids_str = os.getenv('ly_wxid_data')
    if not wxids_str:
        print("❌ 请设置环境变量 ly_wxid_data（每行一个wxid）")
        return []
    
    # 自动检测分隔符
    split_char = None
    for sep in MULTI_ACCOUNT_SPLIT:
        if sep in wxids_str:
            split_char = sep
            break
    
    # 如果没有找到分隔符，默认当作单账号
    if not split_char:
        wxids = [wxids_str.strip()]
    else:
        wxids = [x.strip() for x in wxids_str.split(split_char) if x.strip()]
    
    return wxids

def get_token(wxid):
    """通过wxid获取code并换取token"""
    try:
        # 第一步：通过wxid获取code
        code = wx_code_auth(wxid, APPID)
        if not code:
            print(f"❌ [1/2] 获取code失败 | wxid: {wxid[:8]}...")
            return None
        # print(f"✅ [1/2] 获取code成功 | code: {code}")

        # 第二步：用code获取token（最多重试2次）
        url = f'https://{HOST}/MiniProgramApiCore/api/v3/login/auth'
        data = {
            'Source': 'ldshu',
            'Code': code
        }
        headers = BASE_HEADERS.copy()
        
        for attempt in range(1, 3):
            try:
                resp = requests.put(url, headers=headers, data=json.dumps(data), timeout=15)
                # print(f"📡 [2/2] 接口响应状态码: {resp.status_code}")
                # print(f"📡 [2/2] 接口完整响应: {resp.text}")
                
                resp.raise_for_status()
                result = resp.json()

                if 'token' in result:
                    token = result['token']
                    nickname = f"wxid_{wxid[:8]}"  # 使用wxid前8位作为默认昵称
                    # print(f"✅ [2/2] 获取token成功 | wxid: {wxid[:8]}... | 昵称: {nickname}")
                    return {'token': token, 'nickname': nickname}
                
                print(f"❌ [2/2] 接口返回错误: 响应中缺少token字段")
                return None

            except requests.exceptions.RequestException as e:
                print(f"⚠️ [2/2] 请求失败 (尝试 {attempt}/2): {type(e).__name__}: {str(e)}")
                if attempt == 2:
                    print(f"❌ [2/2] 重试失败 | wxid: {wxid[:8]}...")
                    return None
                time.sleep(2)

    except Exception as e:
        print(f"⚠️ 获取token异常: {type(e).__name__}: {str(e)}")
        return None

def sign_in(account):
    """执行单个账号的签到和查询流程，签到后延迟3秒查询"""
    headers = BASE_HEADERS.copy()
    headers['token'] = account['token']

    print(f"\n🔹 正在处理账号: {account['nickname']} (wxid: {account['wxid'][:8]}...)")

    # 接口1: 签到
    sign_url = f'https://{HOST}/MiniProgramApiCore/api/v3/Login/Sign'
    sign_status = "❌ 签到失败"
    try:
        sign_response = requests.post(sign_url, headers=headers, data='{}')
        # print(f"📡 签到接口响应状态码: {sign_response.status_code}")
        # print(f"📡 签到接口完整响应: {sign_response.text}")
        
        sign_result = sign_response.json()
        if sign_result.get('Success', False):
            sign_status = f"✅ 签到成功，获得积分：{sign_result.get('Data', 0)}"
        else:
            sign_status = f"❌ 签到失败：{sign_result.get('Message', '今日已签到')}"
    except Exception as e:
        sign_status = f"❌ 签到请求失败：{e}"
    
    print(f"📌 签到状态: {sign_status}")

    # 延迟3秒
    print("⏳ 等待3秒后查询用户信息...")
    time.sleep(3)

    # 接口2: 获取积分信息
    try:
        info_url = f'https://{HOST}/MiniProgramApiCore/api/v3/My/GetMyScore'
        info_response = requests.get(info_url, headers=headers)
        # print(f"📡 积分接口响应状态码: {info_response.status_code}")
        # print(f"📡 积分接口完整响应: {info_response.text}")
        
        score = info_response.json()
        if isinstance(score, (int, float)):
            print(f"🪙 当前积分: {int(score)}")
            if int(score) >= 100:
                print("🔁 积分达到100以上，准备提现")
                withdraw(account, int(score))
            else:
                print("⚠️ 积分不足100，不提现")
        else:
            print(f"❌ 积分获取失败：{score}")
    except Exception as e:
        print(f"⚠️ 积分获取请求失败：{e}")

    return sign_status.startswith('✅') or '今日已签到' in sign_status

def withdraw(account, score):
    """执行提现"""
    headers = BASE_HEADERS.copy()
    headers['token'] = account['token']
    
    try:
        url = f'https://{HOST}/MiniProgramApiCore/api/v3/cash/SaveCash'
        data = {
            "AliAccount": "直接到微信钱包的余额",
            "Score": str(score)
        }
        resp = requests.post(url, headers=headers, data=json.dumps(data), timeout=15)
        # print(f"📡 提现接口响应状态码: {resp.status_code}")
        # print(f"📡 提现接口完整响应: {resp.text}")
        
        result = resp.json()
        if result.get('Success'):
            print(f"✅ 提现成功，提现积分：{score}")
        else:
            print(f"❌ 提现失败：{result.get('Message', '未知错误')}")
    except Exception as e:
        print(f"❌ 提现请求失败：{e}")

def main():
    start_time = datetime.now()
    print(f"\n🏁 开始执行... {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    wxids = load_wxids()
    if not wxids:
        return
    
    print(f"📊 共加载 {len(wxids)} 个账号")
    
    success_count = 0
    accounts = []
    
    # 获取每个wxid的token
    for wxid in wxids:
        if auth := get_token(wxid):
            accounts.append({'wxid': wxid, 'token': auth['token'], 'nickname': auth['nickname']})
    
    # 处理签到和查询
    for account in accounts:
        if sign_in(account):
            success_count += 1
    
    end_time = datetime.now()
    duration = (end_time - start_time).seconds
    
    print(f"\n🏁 执行结束... {end_time.strftime('%Y-%m-%d %H:%M:%S')}  耗时 {duration} 秒")
    print(f"📊 任务完成: 成功处理 {success_count}/{len(accounts)} 个账号")

if __name__ == '__main__':
    main()
# 当前脚本来自于http://script.345yun.cn脚本库下载！