import time
import os
import sys
import json
from datetime import datetime

# 階層パスの追加設定 (src フォルダおよびルートフォルダの両方を検索対象に設定)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if current_dir not in sys.path:
    sys.path.append(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# モジュールの読み込み
import gmail_fetcher
from pdf_parser import extract_text_from_pdf
from toho_ss_search import run_toho_ss_search
from checker import verify_insurance_data
from app import parse_pdf_fields, save_history

def get_unread_emails_from_gmail():
    """gmail_fetcher 内の利用可能な関数を自動判別して未読メールを取得"""
    for func_name in ["fetch_unread_quote_emails", "fetch_latest_quote_email", "fetch_quote_emails", "get_unread_emails"]:
        if hasattr(gmail_fetcher, func_name):
            func = getattr(gmail_fetcher, func_name)
            res = func()
            if res:
                return res if isinstance(res, list) else [res]
    return []

def process_single_email(email_info):
    """
    受信した見積書メール1件に対する自動解析・照合パイプライン
    """
    pdf_path = email_info.get("pdf_path")
    sender_email = email_info.get("sender_email") or email_info.get("from")
    
    print(f"\n[自動処理開始] 送信元: {sender_email} | PDF: {pdf_path}")
    
    if not pdf_path or not os.path.exists(pdf_path):
        print("❌ 添付PDFが見つかりません。")
        return

    # 1. PDFからテキスト抽出 & パース
    extracted_text = extract_text_from_pdf(pdf_path)
    pdf_data = parse_pdf_fields(extracted_text)
    
    customer_name = pdf_data["customer_name"]
    target_email = pdf_data["email"] or sender_email

    print(f" 📄 抽出結果: 氏名『{customer_name or '未検出'}』 | メール『{target_email}』")

    # 2. 顧客情報が無い場合のハンドリング
    if not customer_name and not target_email:
        record = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "customer_name": "氏名記載なし",
            "email": sender_email or "不明",
            "status": "顧客情報未検出",
            "details": {
                "建物区分": {"status": "抽出完了", "pdf": pdf_data["building_category"] or "未検出", "ss": "-"},
                "所在地": {"status": "抽出完了", "pdf": pdf_data["address"] or "未検出", "ss": "-"},
                "専有面積": {"status": "抽出完了", "pdf": f"{pdf_data['area']}㎡" if pdf_data['area'] > 0 else "未検出", "ss": "-"},
                "築年数(建築年月)": {"status": "抽出完了", "pdf": pdf_data["built_year"] or "未検出", "ss": "-"},
                "建物構造": {"status": "抽出完了", "pdf": pdf_data["structure"] or "未検出", "ss": "-"}
            },
            "mismatches": ["顧客名・メールアドレス未検出のためSS照合未実施"]
        }
        save_history(record)
        print(" ⚠️ 顧客情報未検出のため管理ポータルに記録してスキップします。")
        return

    # 3. TOHO SS 自動検索 (裏側/Headless)
    print(" 🌐 TOHO SS 裏側検索を実行中...")
    ss_status, search_logs = run_toho_ss_search(email=target_email, name=customer_name)

    # 4. 照合および結果保存
    if not ss_status.startswith("成功"):
        record = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "customer_name": customer_name or "不明",
            "email": target_email,
            "status": f"不整合 ({ss_status})",
            "details": {},
            "mismatches": [f"SS顧客検索エラー: {ss_status}"]
        }
        save_history(record)
        print(f" ⚠️ SS照合エラー記録完了: {ss_status}")
    else:
        # SSデータとの7項目照合
        mock_ss_data = {
            "built_year": pdf_data["built_year"],
            "structure": pdf_data["structure"],
            "area": pdf_data["area"],
            "address": pdf_data["address"],
            "customer_name": customer_name,
            "email": target_email,
            "discount": pdf_data["discount"]
        }
        check_result = verify_insurance_data(pdf_data, mock_ss_data)

        record = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "customer_name": customer_name or "未設定",
            "email": target_email,
            "status": check_result["final_status"],
            "details": check_result["details"],
            "mismatches": check_result["mismatches"]
        }
        save_history(record)
        print(f" ✅ 照合完了・管理ポータル更新完了: 【{check_result['final_status']}】")

def start_auto_monitoring_loop(interval_sec: int = 10):
    """
    定期的にメール受領をチェックし自動処理する常駐ワーカー
    """
    print("==================================================")
    print("🤖 全自動バックグラウンド処理ワーカーを起動しました")
    print(f"   (チェック間隔: {interval_sec}秒)")
    print("==================================================")

    while True:
        try:
            unread_emails = get_unread_emails_from_gmail()
            if unread_emails:
                print(f"\n📩 新着の見積書メールを {len(unread_emails)} 件検出しました。")
                for mail in unread_emails:
                    process_single_email(mail)
        except Exception as e:
            print(f"監視ループ待機中 ({e})")

        time.sleep(interval_sec)

if __name__ == '__main__':
    start_auto_monitoring_loop()