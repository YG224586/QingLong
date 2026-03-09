'''
new Env('MT论坛签到-简化版')
简化版保留核心功能，优化请求逻辑
cron: 0 8 * * *
'''
import requests
import re
import time
import random
from datetime import datetime
from notify import send

class MTBBS:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 15; RMX3852 Build/UKQ1.231108.001) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7339.208 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        }
        self.username = "账号"
        self.password = "密码"

    def safe_request(self, url, method='GET', data=None, retry=2):
        """安全请求函数"""
        for attempt in range(retry):
            try:
                headers = self.headers.copy()
                if method.upper() == 'GET':
                    response = self.session.get(url, headers=headers, timeout=15)
                else:
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    response = self.session.post(url, data=data, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 302:
                    return response
                else:
                    print(f"请求失败，状态码: {response.status_code}")
            except Exception as e:
                print(f"请求异常: {str(e)}")
            
            if attempt < retry - 1:
                time.sleep(random.uniform(2, 4))
        
        return None

    def login(self):
        """登录功能"""
        print("正在登录...")
        
        # 获取登录页面
        login_url = "https://bbs.binmt.cc/member.php?mod=logging&action=login"
        login_resp = self.safe_request(login_url)
        if not login_resp:
            return False, "登录页面获取失败"
        
        # 提取登录参数
        html = login_resp.text
        formhash_match = re.search(r'name="formhash"[^>]*value=[\'"]([^\'"]*)[\'"]', html)
        referer_match = re.search(r'name="referer"[^>]*value="([^"]*)"', html)
        
        if not formhash_match:
            return False, "formhash提取失败"
        
        formhash = formhash_match.group(1)
        referer = referer_match.group(1) if referer_match else "https://bbs.binmt.cc/forum.php"
        
        # 构造登录数据
        login_data = {
            'formhash': formhash,
            'referer': referer,
            'username': self.username,
            'password': self.password,
            'loginsubmit': 'true'
        }
        
        # 提交登录
        login_post_url = "https://bbs.binmt.cc/member.php?mod=logging&action=login&loginsubmit=yes&inajax=1"
        login_result = self.safe_request(login_post_url, 'POST', login_data)
        
        if not login_result:
            return False, "登录请求失败"
        
        # 检查登录结果
        if '登录成功' in login_result.text or 'window.location.href' in login_result.text:
            return True, "登录成功"
        elif '密码错误' in login_result.text:
            return False, "账号或密码错误"
        else:
            return False, "登录失败"

    def sign_in(self):
        """签到功能"""
        print("正在签到...")
        
        # 访问签到页面
        sign_url = "https://bbs.binmt.cc/k_misign-sign.html"
        sign_resp = self.safe_request(sign_url)
        if not sign_resp:
            return "签到页面访问失败"
        
        # 提取formhash
        formhash_match = re.search(r'formhash=([a-f0-9]+)', sign_resp.text)
        if not formhash_match:
            return "formhash提取失败"
        
        formhash = formhash_match.group(1)
        
        # 执行签到
        sign_post_url = f"https://bbs.binmt.cc/plugin.php?id=k_misign:sign&operation=qiandao&format=text&formhash={formhash}"
        sign_result = self.safe_request(sign_post_url)
        
        if not sign_result:
            return "签到请求失败"
        
        result_text = sign_result.text.strip()
        
        if "今日已签" in result_text:
            return "今日已完成签到"
        elif "签到成功" in result_text:
            # 提取奖励信息
            reward_match = re.search(r'获得奖励\s*(\S+)', result_text)
            reward = reward_match.group(1) if reward_match else "未知奖励"
            return f"签到成功！获得：{reward}"
        else:
            return f"签到异常：{result_text[:30]}"

    def get_credit(self):
        """获取积分信息"""
        credit_url = "https://bbs.binmt.cc/home.php?mod=spacecp&ac=credit"
        credit_resp = self.safe_request(credit_url)
        
        if not credit_resp:
            return "积分信息获取失败"
        
        info = []
        patterns = [
            (r'金币:\s*</span>(\d+)\s*&nbsp;', '金币'),
            (r'威望:\s*</span>(\d+)', '威望'),
            (r'热心:\s*</span>(\d+)', '热心'),
        ]
        
        for pattern, name in patterns:
            match = re.search(pattern, credit_resp.text)
            if match:
                info.append(f"{name}:{match.group(1)}")
        
        return " | ".join(info) if info else "积分数据提取失败"

    def run(self):
        """主运行流程"""
        print("=" * 30)
        print("MT论坛签到开始")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 30)
        
        # 随机延迟
        time.sleep(random.uniform(1, 3))
        
        # 登录
        login_ok, login_msg = self.login()
        if not login_ok:
            result = f"❌ 登录失败: {login_msg}"
            print(result)
            return result
        
        print("✅ 登录成功")
        time.sleep(1)
        
        # 签到
        sign_msg = self.sign_in()
        print(f"签到结果: {sign_msg}")
        
        # 获取积分
        credit_info = self.get_credit()
        print(f"账户信息: {credit_info}")
        
        # 构造结果
        result = (
            f"【MT论坛签到结果】\n"
            f"账号: {self.username}\n"
            f"签到: {sign_msg}\n"
            f"账户: {credit_info}\n"
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        return result

if __name__ == "__main__":
    try:
        mt = MTBBS()
        result = mt.run()
        
        print("\n" + "=" * 30)
        print("最终结果:")
        print(result)
        print("=" * 30)
        
        # 发送通知
        send('MT论坛签到', result)
        print("通知发送成功")
        
    except Exception as e:
        error_msg = f"MT论坛签到异常: {str(e)}"
        print(error_msg)
        send('MT论坛签到异常', error_msg)