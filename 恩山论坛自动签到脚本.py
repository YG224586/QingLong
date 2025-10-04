"""
脚本名称: 恩山论坛自动签到脚本
脚本版本：1.8
脚本说明：自动签到 成功后获取积分明细
更新说明：1.8限制积分记录显示数量（只展示最近3条）；优化记录展示紧凑性
1.7修复积分信息提取失败问题；移除积分记录中的HTML标签；增强错误处理
1.6修复积分记录正则表达式，适配页面4列结构；修正积分提取逻辑
1.5修正正则表达式以匹配积分记录
1.4优化了获取积分详情的正则表达式模式,得到更完整的积分明细
1.3恩山签到及积分记录
1.0自动签到
使用说明：在环境变量设置了一个名为enshanck的变量，用于存储恩山论坛的cookie
抓包https://www.right.com.cn/forum/home.php?mod=spacecp&ac=credit&op=base这个页面的cookie
"""

import re
import os
import notify
import requests

# 从环境变量获取恩山论坛的cookie
enshanck = os.getenv("enshanck")

# 配置请求头
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.97 Safari/537.36",
    "Cookie": enshanck,
    "Referer": "https://www.right.com.cn/forum/home.php?mod=spacecp&ac=credit",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9"
}

session = requests.Session()
res = ""
MAX_RECORDS = 3  # 最多显示3条记录（可根据需要调整）

try:
    # 签到并获取积分主页
    response = session.get(
        'https://www.right.com.cn/forum/home.php?mod=spacecp&ac=credit&showcredit=1',
        headers=headers,
        timeout=10
    )
    response.raise_for_status()
    response.encoding = "utf-8"

    # 积分提取逻辑
    total_point_match = re.search(r'<a id="extcreditmenu".*?>积分: (\d+)<\/a>', response.text)
    if not total_point_match:
        total_point_match = re.search(r'积分[:：]\s*(\d+)', response.text)
    
    if total_point_match:
        total_point = total_point_match.group(1)
        res += f"恩山签到\n恩山币：{total_point}\n积分：{total_point}\n"
    else:
        res += "恩山签到\n警告：未获取到总积分\n"

except requests.exceptions.RequestException as e:
    res += f"签到请求失败: {str(e)}\n"
except Exception as e:
    res += f"积分信息处理异常: {str(e)}\n"

# 获取积分记录（限制显示数量）
try:
    record_response = session.get(
        'https://www.right.com.cn/forum/home.php?mod=spacecp&ac=credit&op=log',
        headers=headers,
        timeout=10
    )
    record_response.raise_for_status()
    record_response.encoding = "utf-8"

    pattern = r'<tr>\s*<td><a href=".*?">(.*?)<\/a><\/td>\s*<td>(.*?)<\/td>\s*<td>(.*?)<\/td>\s*<td>(.*?)<\/td>\s*<\/tr>'
    matches = re.findall(pattern, record_response.text)

    if matches:
        res += f"恩山签到积分记录（最近{MAX_RECORDS}条）\n"
        displayed = 0  # 已显示记录计数
        for match in matches:
            # 过滤表头行
            if "操作" in match[0] or "积分变更" in match[1]:
                continue
            
            # 控制显示数量
            if displayed >= MAX_RECORDS:
                break
            
            # 清洗数据
            action = re.sub(r'<.*?>', '', match[0]).strip()
            credit_change = re.sub(r'<.*?>', '', match[1]).strip()
            detail = re.sub(r'<.*?>', '', match[2]).strip()
            time = re.sub(r'<.*?>', '', match[3]).strip()

            displayed += 1
            res += (
                f"记录 {displayed}:\n"
                f"操作: {action}\n"
                f"积分变更: {credit_change}\n"
                f"详情: {detail}\n"
                f"时间: {time}\n\n"
            )
    else:
        res += "未找到积分记录信息\n"

except requests.exceptions.RequestException as e:
    res += f"积分记录请求失败: {str(e)}\n"
except Exception as e:
    res += f"积分记录处理异常: {str(e)}\n"

# 发送通知
if res:
    print(res)
    notify.send("恩山签到及积分记录", res)
else:
    print("未找到相关信息")