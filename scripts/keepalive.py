#!/usr/bin/env python3
"""
IBKR Session Keepalive + Auto-Relogin Script
每 5 分钟由 cron 执行，自动保活会话，掉线后自动重新登录。

功能：
1. 发送 tickle 保持会话活跃
2. 如果会话过期，通过 Selenium 自动重新登录（无需手机 2FA）
3. 如果 Gateway 进程都没跑，打日志等 launchd 自愈

Crontab entry:
*/5 * * * * cd ~/trading && venv/bin/python /path/to/keepalive.py >> ~/trading/keepalive.log 2>&1
"""

import requests
import urllib3
import os
import sys
import time
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = os.getenv("IBEAM_GATEWAY_BASE_URL", "https://localhost:5001")
TRADING_DIR = os.getenv("TRADING_DIR", os.path.expanduser("~/trading"))

def log(msg):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} {msg}")

def check_auth_status():
    """Check if session is authenticated."""
    try:
        r = requests.get(
            f"{BASE_URL}/v1/api/iserver/auth/status",
            verify=False,
            timeout=10
        )
        data = r.json()
        return data.get("authenticated", False), data
    except requests.exceptions.ConnectionError:
        return False, {"error": "Gateway not running (Connection refused)"}
    except Exception as e:
        return False, {"error": str(e)}

def tickle():
    """Send keepalive ping."""
    try:
        r = requests.post(
            f"{BASE_URL}/v1/api/tickle",
            verify=False,
            timeout=10
        )
        return r.status_code == 200
    except:
        return False

def load_env():
    """从 .env 加载凭证"""
    env_file = os.path.join(TRADING_DIR, ".env")
    env = {}
    try:
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env[key] = value.strip("'").strip('"')
    except:
        pass
    return env

def auto_relogin():
    """
    通过 Selenium 自动化 Chrome 完成 Client Portal 登录。
    适用于不需要 2FA 的专用 bot 账户。
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
    except ImportError:
        log("❌ Selenium 未安装，无法自动重登")
        return False
    
    env = load_env()
    username = env.get("IBEAM_ACCOUNT", "")
    password = env.get("IBEAM_PASSWORD", "")
    
    if not username or not password:
        log("❌ .env 中缺少 IBEAM_ACCOUNT 或 IBEAM_PASSWORD")
        return False
    
    log(f"🌐 启动 Selenium 自动登录 (用户: {username})...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--allow-insecure-localhost")
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        
        login_url = f"{BASE_URL}/sso/Login?forwardTo=22&RL=1&ip2loc=US"
        driver.get(login_url)
        time.sleep(3)
        
        wait = WebDriverWait(driver, 20)
        
        # 填入用户名
        user_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        user_field.clear()
        user_field.send_keys(username)
        
        # 填入密码
        pass_field = driver.find_element(By.NAME, "password")
        pass_field.clear()
        pass_field.send_keys(password)
        
        # 提交
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            btn.click()
        except:
            pass_field.send_keys(Keys.RETURN)
        
        log("🚀 登录表单已提交，等待认证...")
        
        # 等待认证完成
        for i in range(30):
            time.sleep(2)
            auth_ok, _ = check_auth_status()
            if auth_ok:
                log("✅ 自动重登成功！")
                return True
        
        log("❌ 60秒内未完成认证")
        return False
        
    except Exception as e:
        log(f"❌ Selenium 错误: {e}")
        return False
    finally:
        if driver:
            driver.quit()

def main():
    auth_ok, status = check_auth_status()
    
    if "error" in status:
        log(f"❌ Gateway not responding: {status['error']}")
        log("   等待 launchd 自动重启 Gateway...")
        return
    
    if auth_ok:
        # Session active → tickle 续命
        if tickle():
            log("✅ Session active - keepalive sent")
        else:
            log("⚠️ Tickle failed but session reports authenticated")
    else:
        # Session expired → 自动重登
        log("⚠️ Session not authenticated - attempting auto-relogin...")
        if auto_relogin():
            log("🎉 Auto-relogin successful, session restored")
        else:
            log("❌ Auto-relogin failed. Manual login may be needed.")
            log("   Run: cd ~/trading && venv/bin/python manual_auth.py")

if __name__ == "__main__":
    main()
