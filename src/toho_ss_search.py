import os
import json
import time
from playwright.sync_api import sync_playwright

STATE_FILE = "credentials/state.json"

def run_toho_ss_search(email: str = "", name: str = "") -> tuple[str, list]:
    """
    TOHO SS にログインし、顧客検索（一次: メールアドレス / 予備: 氏名）を実行する（完全可視化版）
    """
    status = "SS未検出"
    logs = []
    has_session = os.path.exists(STATE_FILE)

    with sync_playwright() as p:
        logs.append("🌐 Playwright ブラウザエンジンを起動中...（画面表示モード）")
        # headless=False によりブラウザを画面上に表示して操作を目視可能にします
        browser = p.chromium.launch(headless=False, slow_mo=500)

        if has_session:
            logs.append("💾 保存済みのログインセッション (state.json) を読み込みました。")
            context = browser.new_context(storage_state=STATE_FILE)
        else:
            logs.append("⚠️ 保存済みセッションなし。新規ログインを実行します。")
            context = browser.new_context()

        page = context.new_page()

        try:
            # 1. ログイン画面・トップ画面へアクセス
            logs.append("🔗 ページへアクセス: https://toho-ss.jp/es/login/next")
            page.goto("https://toho-ss.jp/es/login/next", timeout=30000)
            page.wait_for_timeout(1000)

            # 未ログインの場合の自動ログイン
            if "login" in page.url or page.locator("input[name='loginId']").is_visible():
                logs.append("🔑 ID/パスワードを入力中...")
                page.fill("input[name='loginId']", "okuyama@toho-next.com")
                page.fill("input[name='password']", "next2026")
                page.click("button[type='submit']")

                logs.append("⚡ ログイン完了を監視中...")
                page.wait_for_selector("text=顧客管理", timeout=30000)
                logs.append("⚡ ログイン完了・ヘッダー描画を確認しました！")

                os.makedirs("credentials", exist_ok=True)
                context.storage_state(path=STATE_FILE)
                logs.append("💾 ログイン認証情報を `credentials/state.json` に保存しました。")

            # 2. 顧客検索画面へ遷移
            logs.append("📌 『顧客検索』画面へ切り替え中...")
            if page.locator("text=顧客検索").is_visible():
                page.click("text=顧客検索")
            else:
                page.goto("https://toho-ss.jp/es/customer/search", timeout=30000)

            page.wait_for_selector("input[name='searchWord']", timeout=10000)
            logs.append("🎯 顧客検索画面に到着！自動検索を開始します。")

            found_customer = False

            # 3. 一次検索 (メールアドレス)
            if email:
                logs.append(f"🔍 [一次検索] メールアドレス `{email}` を入力中...")
                page.fill("input[name='searchWord']", email)
                page.click("button:has-text('検索')")
                page.wait_for_timeout(2000)

                # 検索結果の判定
                if not page.locator("text=該当するデータが見つかりません").is_visible() and page.locator("table tbody tr").count() > 0:
                    logs.append("✅ [一次検索成功] メールアドレスで顧客データを検出しました！")
                    found_customer = True

            # 4. 予備検索 (氏名)
            if not found_customer and name:
                logs.append(f"⚠️ 宛先メールアドレスで未ヒット。予備検索 (氏名) へ移行します...")
                page.fill("input[name='searchWord']", name)
                page.click("button:has-text('検索')")
                page.wait_for_timeout(2000)

                if not page.locator("text=該当するデータが見つかりません").is_visible() and page.locator("table tbody tr").count() > 0:
                    logs.append(f"✅ [予備検索成功] 氏名 `{name}` で顧客データを検出しました！")
                    found_customer = True
                else:
                    # スペース除去で再検索
                    clean_name = name.replace(" ", "").replace(" ", "")
                    logs.append(f"🔍 [予備検索再試行] スペースなし `{clean_name}` で再検索中...")
                    page.fill("input[name='searchWord']", clean_name)
                    page.click("button:has-text('検索')")
                    page.wait_for_timeout(2000)

                    if not page.locator("text=該当するデータが見つかりません").is_visible() and page.locator("table tbody tr").count() > 0:
                        logs.append(f"✅ [予備検索成功] スペースなし氏名 `{clean_name}` で検出しました！")
                        found_customer = True

            if found_customer:
                status = "成功 (顧客データ検出済)"
            else:
                logs.append("❌ [失敗] 検索条件に合致する顧客データはTOHO SSに存在しません。")
                status = "SS未検出"

        except Exception as e:
            logs.append(f"❌ エラーが発生しました: {str(e)}")
            status = f"エラー ({str(e)})"
        finally:
            browser.close()

    return status, logs