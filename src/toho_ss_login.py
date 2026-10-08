import os
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ログインセッション情報の保存先
SESSION_FILE = "credentials/toho_ss_cookies.json"
LOGIN_URL = "https://toho-ss.jp/es/login/next"

def save_login_session():
    """
    Seleniumを使用してGoogle Chromeを起動し、
    手動でログイン・2段階認証を行った後に Cookie を保存する
    """
    os.makedirs("credentials", exist_ok=True)
    
    print("----------------------------------------")
    print("Google Chrome ブラウザを起動します...")
    print("----------------------------------------")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(LOGIN_URL)
        
        print("\n----------------------------------------")
        print(f"TOHO SS ログインページを開きました: {LOGIN_URL}")
        print("ID・パスワードを入力し、二段階認証を完了してログインしてください。")
        print("----------------------------------------")
        
        # ユーザーがログインを完了するのを待機
        input("\n★ ブラウザ上で2段階認証・ログインが完了したら、このターミナルで Enter キーを押してください...")
        
        # ログイン後の Cookie 情報を取得して保存
        cookies = driver.get_cookies()
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
            
        print(f"\n[成功] ログインセッション(Cookie)を保存しました: {SESSION_FILE}")
        
    finally:
        driver.quit()

if __name__ == '__main__':
    save_login_session()