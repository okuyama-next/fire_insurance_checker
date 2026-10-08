import os
import glob
from pdf_parser import extract_text_from_pdf, get_latest_pdf
from toho_ss_search import run_toho_ss_search
from checker import verify_insurance_data

def run_full_pipeline_test():
    print("==================================================")
    print("🚀 【一連挙動テスト開始】 Phase 2 ～ Phase 3 パイプライン")
    print("==================================================")

    # 1. downloads フォルダから最新のPDFを取得してテキスト抽出
    latest_pdf = get_latest_pdf()
    if not latest_pdf:
        print("❌ エラー: downloads フォルダ内にテスト用PDFが見つかりません。")
        return

    print(f"\n📄 [STEP 1] 最新PDFからのテキストダイレクト抽出: {latest_pdf}")
    pdf_text = extract_text_from_pdf(latest_pdf)
    print("--- 抽出テキスト (冒頭300文字) ---")
    print(pdf_text[:300] + "...")
    print("-----------------------------------")

    # PDFテキストから擬似的に抽出データを構造化（動作確認用パラメータ）
    parsed_pdf_data = {
        "built_year": "令和8年9月",
        "structure": "戸建て H構造",
        "area": 107.72,
        "address": "東京都西東京市住吉町4丁目",
        "customer_name": "奥山由佳",
        "email": "okuyama@toho-next.com",
        "discount": "耐震等級割引(50%)"
    }

    # 2. TOHO SS への自動検索（state.json が存在するため裏側 Headless 実行）
    print(f"\n🌐 [STEP 2] TOHO SS への自動検索 (一次: {parsed_pdf_data['email']} / 予備: {parsed_pdf_data['customer_name']})")
    ss_status, search_logs = run_toho_ss_search(
        email=parsed_pdf_data['email'],
        name=parsed_pdf_data['customer_name']
    )

    print("--- RPA実行ログ ---")
    for log in search_logs:
        print(f"  {log}")
    print(f"-> 検索ステータス: {ss_status}")

    # 3. TOHO SSから取得した擬似データとの7項目照合テスト
    print("\n🔍 [STEP 3] 7項目自動照合エンジンの実行")
    # テスト用のTOHO SSデータ（模擬データ）
    mock_ss_data = {
        "built_year": "令和8年9月17日",
        "structure": "戸建て H構造",
        "area": 107.50, # 誤差0.22㎡ (1.0㎡以内なのでOK)
        "address": "東京都西東京市住吉町4丁目",
        "customer_name": "奥山由佳",
        "email": "okuyama@toho-next.com",
        "discount": "耐震等級割引(50%)"
    }

    check_result = verify_insurance_data(parsed_pdf_data, mock_ss_data)

    print("\n==================================================")
    print(f"📊 【最終照合結果】: {check_result['final_status']}")
    print("==================================================")
    for item_name, detail in check_result["details"].items():
        print(f" ・{item_name}: [{detail['status']}] (PDF: {detail['pdf']} / SS: {detail['ss']})")
    print("==================================================")

if __name__ == '__main__':
    run_full_pipeline_test()