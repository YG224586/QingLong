# 当前脚本来自于http://script.345yun.cn脚本库下载！
import os
import requests
import time

def main():
    cookie_info = os.getenv("FQXS_COOKIE")
    if not cookie_info:
        print("请在环境变量中设置 FQXS_COOKIE，格式为 sessionid#iid#device_id")
        return
    parts = cookie_info.split("#")
    if len(parts) != 3:
        print("FQXS_COOKIE 格式不正确，应为 sessionid#iid#device_id")
        return
    sessionid, iid, device_id = parts
    headers = {
        "Cookie": f"sessionid={sessionid}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    host = os.getenv("FQXS_HOST", "i-hl.snssdk.com")

    list_url = f"https://{host}/luckycat/novel/v1/task/list"
    params = {
        "sessionid": sessionid,
        "iid": iid,
        "device_id": device_id,
        "polaris_page": "client_task_page",
        "new_bookshelf": "1"
    }
    try:
        res = requests.get(list_url, headers=headers, params=params, timeout=10)
        data = res.json()
    except Exception as e:
        print(f"获取任务列表失败: {e}")
        return

    daily = data.get("data", {}).get("task_list", {}).get("daily", [])

    # 签到任务
    sign_task = next((item for item in daily if item.get("task_id") == 203), None)
    if sign_task and not sign_task.get("completed"):
        sign_url = f"https://{host}/luckycat/novel/v1/task/done/sign_in"
        try:
            res_sign = requests.post(sign_url, headers=headers, params=params, json={}, timeout=10)
            result = res_sign.json()
            if result.get("err_no") == 0:
                amount = result['data']['amount']
                print(f"签到成功，获得 {amount} 金币")
            else:
                print(f"签到失败: {result.get('err_tips', '未知错误')}")
        except Exception as e:
            print(f"签到请求失败: {e}")
    else:
        print("签到任务已完成或不可用。")

    # 阅读任务
    read_tasks = {5: 1006, 10: 1003, 30: 1009, 60: 1010, 120: 1011, 180: 1012}
    for minutes, task_id in read_tasks.items():
        task = next((item for item in daily if item.get("task_id") == task_id), None)
        if task and not task.get("completed"):
            read_url = f"https://{host}/luckycat/novel/v1/task/done/daily_read_{minutes}m"
            payload = {"new_bookshelf": True, "task_key": f"daily_read_{minutes}m"}
            try:
                res_read = requests.post(read_url, headers=headers, params=params, json=payload, timeout=10)
                result = res_read.json()
                if result.get("err_no") == 0:
                    amount = result['data']['amount']
                    print(f"阅读 {minutes} 分钟任务完成，获得 {amount} 金币")
                else:
                    print(f"阅读 {minutes} 分钟任务提示: {result.get('err_tips', '未知')}")
            except Exception as e:
                print(f"阅读 {minutes} 分钟请求失败: {e}")
            time.sleep(1)
        else:
            print(f"{minutes} 分钟阅读任务已完成或不存在。")

    # 看广告任务
    video_task = next((item for item in daily if item.get("task_id") == 111), None)
    if video_task and not video_task.get("completed"):
        ad_url = f"https://{host}/luckycat/novel/v1/task/done/excitation_ad"
        payload = {"new_bookshelf": True, "task_key": "excitation_ad"}
        try:
            res_ad = requests.post(ad_url, headers=headers, params=params, json=payload, timeout=10)
            result = res_ad.json()
            if result.get("err_no") == 0:
                amount = result['data']['amount']
                print(f"观看广告视频任务完成，获得 {amount} 金币")
            else:
                print(f"广告任务提示: {result.get('err_tips', '未知')}")
        except Exception as e:
            print(f"广告任务请求失败: {e}")
    else:
        print("广告任务已完成或不存在。")

    print("番茄小说任务执行完毕。")

if __name__ == "__main__":
    main()
# 当前脚本来自于http://script.345yun.cn脚本库下载！