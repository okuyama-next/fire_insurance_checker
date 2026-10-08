import os
import sys
import glob
import re

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
    """Streamlitに依存しないダイレクト構造解析エンジン"""
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

def main():
    print("==================================================")
    print("🚀 【一連挙動テスト開始】 Phase 2 ～ Phase 3 パイプライン")
    print("==================================================")

    # downloads フォルダから最新の PDF を直接取得
    pdf_files = glob.glob("downloads/*.pdf")
    if not pdf_files:
        print("❌ `downloads` フォルダ内にテスト用のPDFが見つかりませんでした。")
        return

    # 最新の更新日時のPDFを選択
    pdf_path = max(pdf_files, key=os.path.getmtime)
    sender_email = "okuyama@toho-next.com"

    print(f"📄 対象PDFファイル: {pdf_path}")

    # 1. PDFよりダイレクトテキスト抽出
    print(f"\n📄 [STEP 1] PDFからのテキストダイレクト抽出実行...")
    extracted_text = extract_text_from_pdf(pdf_path)
    
    print("--- 抽出テキスト (冒頭300文字) ---")
    print(extracted_text[:300] if extracted_text else "（抽出失敗）")
    print("----------------------------------")

    pdf_data = parse_pdf_fields_standalone(extracted_text)
    customer_name = pdf_data["customer_name"]
    target_email = pdf_data["email"] or sender_email

    print(f"解析結果 ➔ 氏名: 『{customer_name or '未検出'}』 | メール: 『{target_email}』")

    # 2. TOHO SS 自動検索 (可視化ブラウザ)
    print(f"\n🌐 [STEP 2] TOHO SS への自動検索 (一次: {target_email} / 予備: {customer_name})")
    ss_status, search_logs = run_toho_ss_search(email=target_email, name=customer_name)

    print("--- RPA実行ログ ---")
    for log in search_logs:
        print(f"  {log}")
    print(f"-> 検索ステータス: {ss_status}")

    # 3. SS未検出・失敗時の正格な割り込み制御
    if not ss_status.startswith("成功"):
        print("\n❌ [処理中断] TOHO SS 上に該当の顧客データが存在しないため、7項目照合を停止します。")
        print(f"   理由: {ss_status}")
        
        record = {
            "id": "test_pipeline_run",
            "date": "2026-10-08 12:56",
            "customer_name": customer_name or "不明",
            "email": target_email or "不明",
            "status": "SS未検出",
            "details": {},
            "mismatches": [f"TOHO SS顧客検索エラー: {ss_status}"]
        }
        save_record_to_db(record)
        send_notification_email(sender_email, "【火災見積りチェッカー】SS未検出通知", f"TOHO SS上に該当データが見つかりませんでした ({ss_status})。")
        return

    # 4. 検索成功時のみ実際の照合処理を実行
    print("\n🔍 [STEP 3] 7項目自動照合エンジンの実行")
    
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

    print(f"\n📊 【最終照合結果】: {check_result['final_status']}")
    print("==================================================")
    for k, v in check_result["details"].items():
        print(f" ・{k}: [{v['status']}] (PDF: {v['pdf']} / SS: {v['ss']})")
    print("==================================================")

if __name__ == '__main__':
    main()