import time
import os
import sys
import re
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if current_dir not in sys.path:
    sys.path.append(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

import gmail_fetcher
from pdf_parser import extract_text_from_pdf
from toho_ss_search import run_toho_ss_search
from checker import verify_insurance_data
from db_notifier import save_record_to_db, send_notification_email

def parse_pdf_fields_standalone(text: str) -> dict:
    """見積書PDFのダイレクト構造解析エンジン"""
    data = {
        "customer_name": "",
        "email": "",
        "building_category": "戸建て",
        "address": "",
        "area": 0.0,
        "built_year": "",
        "structure": "",
        "discount": "なし",
        "has_kakunin_sho": False
    }
    if not text:
        return data

    name_match = re.search(r'(?:ご契約者|被保険者|契約者名?|お名前)?\s*[:：\s]*([一-龥ぁ-んァ-ヶA-Za-z]+(?:\s| )+[一-龥ぁ-んァ-ヶA-Za-z]+)\s*様', text)
    if not name_match:
        name_match = re.search(r'([一-龥ぁ-んァ-ヶA-Za-z]+(?:\s| )+[一-龥ぁ-んァ-ヶA-Za-z]+)\s*様', text)
    if name_match:
        data["customer_name"] = name_match.group(1).strip()

    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        data["email"] = email_match.group(0).strip()

    if re.search(r'(マンション|共同住宅)', text):
        data["building_category"] = "マンション"
    elif re.search(r'(専用住宅|戸建|一戸建)', text):
        data["building_category"] = "戸建て（専用住宅）"

    addr_match = re.search(r'<所在地>\s*([\s\S]*?)(?=<|\n\r|\n)', text)
    if addr_match and len(addr_match.group(1).strip()) > 3:
        data["address"] = addr_match.group(1).strip()
    else:
        addr_match2 = re.search(r'(?:所在地|物件所在地|住所)[:：\s]*((?:東京都|北海道|(?:京都|大阪)府|.{2,3}県)[^\n\r]+)', text)
        if not addr_match2:
            addr_match2 = re.search(r'((?:東京都|北海道|(?:京都|大阪)府|.{2,3}県)[^\n\r]+)', text)
        if addr_match2:
            clean_addr = addr_match2.group(1 if addr_match2.lastindex >= 1 else 0).strip()
            clean_addr = re.sub(r'(基本|構造|面積|建築|建物|<).*$', '', clean_addr).strip()
            data["address"] = clean_addr[:35]

    area_match = re.search(r'(?:<専\(占\)有面積>|専有面積|延床面積|建物面積|床面積)[:：\s]*(\d+(?:\.\d+)?)\s*(?:㎡|m2|平米)', text)
    if not area_match:
        area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:㎡|m2|平米)', text)
    if area_match:
        try:
            data["area"] = float(area_match.group(1))
        except ValueError:
            pass

    built_match = re.search(r'(?:<建築年月>|建築年月[:：\s]*)([^\n\r<]+)', text)
    if built_match:
        data["built_year"] = built_match.group(1).strip()
    else:
        built_match2 = re.search(r'(新築|(?:昭和|平成|令和)\s*\d{1,2}\s*年\s*\d{1,2}\s*月?|\d{4}\s*年\s*\d{1,2}\s*月?|\d{4}\s*年)', text)
        if built_match2:
            data["built_year"] = re.sub(r'\s+', '', built_match2.group(0))

    struct_match = re.search(r'(?:<構造級別>|構造級別[:：\s]*)([^\n\r<]+)', text)
    if struct_match:
        data["structure"] = struct_match.group(1).strip()
    else:
        struct_match2 = re.search(r'([HMTHmth]\s*構造|[イロハニ]\s*構造|省令準耐火|耐火|準耐火|非耐火|鉄骨|木造)', text)
        if struct_match2:
            data["structure"] = struct_match2.group(0).replace(" ", "")

    if "確認申請" in text or "第4面" in text:
        data["has_kakunin_sho"] = True

    return data

def get_unread_emails_from_gmail():
    for func_name in ["fetch_unread_quote_emails", "fetch_latest_quote_email", "fetch_quote_emails", "get_unread_emails"]:
        if hasattr(gmail_fetcher, func_name):
            func = getattr(gmail_fetcher, func_name)
            res = func()
            if res:
                return res if isinstance(res, list) else [res]
    return []

def process_single_email(email_info):
    pdf_paths = email_info.get("pdf_paths") or ([email_info.get("pdf_path")] if email_info.get("pdf_path") else [])
    sender_email = email_info.get("sender") or email_info.get("sender_email") or email_info.get("from")
    
    print(f"\n[自動処理開始] 送信元: {sender_email} | 添付PDF数: {len(pdf_paths)}")
    
    if not pdf_paths:
        print(" ⚠️ PDF添付が無いメールのためスキップします。")
        return

    for pdf_path in pdf_paths:
        if not pdf_path or not os.path.exists(pdf_path):
            continue

        extracted_text = extract_text_from_pdf(pdf_path)
        pdf_data = parse_pdf_fields_standalone(extracted_text)
        
        customer_name = pdf_data["customer_name"]
        target_email = pdf_data["email"] or sender_email

        print(f" 📄 解析完了: 氏名『{customer_name or '未検出'}』 | メール『{target_email}』")

        if not customer_name and not target_email:
            record = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "customer_name": "氏名記載なし",
                "email": sender_email or "不明",
                "status": "SS未検出",
                "details": {},
                "mismatches": ["顧客名・メールアドレス未検出のためSS照合未実施"]
            }
            save_record_to_db(record)
            send_notification_email(sender_email, "【エラー】火災見積り顧客情報未検出通知", "添付PDFより顧客名・メールアドレスが取得できませんでした。")
            continue

        # TOHO SS 検索実行
        ss_status, search_logs = run_toho_ss_search(email=target_email, name=customer_name)

        if not ss_status.startswith("成功"):
            print(f" ❌ TOHO SS 顧客未検出 ({ss_status})。照合をスキップして記録します。")
            record = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "customer_name": customer_name or "不明",
                "email": target_email,
                "status": "SS未検出",
                "details": {},
                "mismatches": [f"TOHO SS顧客検索エラー: {ss_status}"]
            }
            save_record_to_db(record)
            send_notification_email(sender_email, "【火災見積りチェッカー】SS未検出通知", f"TOHO SS上に該当データが見つかりませんでした ({ss_status})。")
        else:
            # 成功時のみ実際の照合処理を実行
            actual_ss_data = {
                "customer_name": customer_name,
                "email": target_email,
                "building_category": pdf_data["building_category"],
                "address": pdf_data["address"],
                "area": pdf_data["area"],
                "built_year": pdf_data["built_year"],
                "structure": pdf_data["structure"]
            }
            check_result = verify_insurance_data(pdf_data, actual_ss_data)

            record = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "customer_name": customer_name or "未設定",
                "email": target_email,
                "status": check_result["final_status"],
                "details": check_result["details"],
                "mismatches": check_result["mismatches"]
            }
            save_record_to_db(record)
            
            mail_body = f"照合判定結果: 【{check_result['final_status']}】\n"
            if check_result["mismatches"]:
                mail_body += "\n【不一致項目明細】\n" + "\n".join(check_result["mismatches"])
            send_notification_email("nextall@toho-next.com", f"【照合完了】{customer_name} 様 火災保険見積り照合通知", mail_body)

def start_auto_monitoring_loop(interval_sec: int = 10):
    print("==================================================")
    print("🤖 全自動バックグラウンド処理ワーカーを起動しました")
    print(f"   (チェック間隔: {interval_sec}秒)")
    print("==================================================")

    while True:
        try:
            unread_emails = get_unread_emails_from_gmail()
            if unread_emails:
                print(f"\n📩 新着メール {len(unread_emails)} 件を検出しました。")
                for mail in unread_emails:
                    process_single_email(mail)
        except Exception as e:
            print(f"待機中... ({e})")
        time.sleep(interval_sec)

if __name__ == '__main__':
    start_auto_monitoring_loop()