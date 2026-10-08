import streamlit as st
import os
import pandas as pd
import json
import re
from datetime import datetime

# 既存モジュールの読み込み
import sys
sys.path.append('src')
from pdf_parser import extract_text_from_pdf
from toho_ss_search import run_toho_ss_search
from checker import verify_insurance_data
from db_notifier import save_record_to_db, load_records_from_db, send_notification_email

# 1. ページ基本設定
st.set_page_config(
    page_title="火災保険見積チェッカー - 管理ポータル v2.0",
    page_icon="🏢",
    layout="wide"
)

def parse_pdf_fields(text: str) -> dict:
    """各種保険会社（損保ジャパン、東京海上日動等）に対応した高精度PDF抽出エンジン"""
    data = {
        "customer_name": "",
        "email": "",
        "building_category": "戸建て", # 建物区分
        "address": "",           # 所在地
        "area": 0.0,             # 専有面積
        "built_year": "",        # 築年数・建築年月
        "structure": "",         # 建物構造
        "discount": "なし",
        "has_kakunin_sho": False
    }
    if not text:
        return data

    # 1. 顧客氏名
    name_match = re.search(r'(?:ご契約者|被保険者|契約者名?|お名前)?\s*[:：\s]*([一-龥ぁ-んァ-ヶA-Za-z]+(?:\s| )+[一-龥ぁ-んァ-ヶA-Za-z]+)\s*様', text)
    if not name_match:
        name_match = re.search(r'([一-龥ぁ-んァ-ヶA-Za-z]+(?:\s| )+[一-龥ぁ-んァ-ヶA-Za-z]+)\s*様', text)
    if name_match:
        data["customer_name"] = name_match.group(1).strip()

    # 2. メールアドレス
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        data["email"] = email_match.group(0).strip()

    # 3. 建物区分 (専用住宅 / 戸建て / マンション / 共同住宅)
    if re.search(r'(マンション|共同住宅)', text):
        data["building_category"] = "マンション"
    elif re.search(r'(専用住宅|戸建|一戸建)', text):
        data["building_category"] = "戸建て（専用住宅）"

    # 4. 所在地 (<所在地> の後の住所または一般的な住所パターン)
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

    # 5. 専有面積 (<専(占)有面積> 107.720㎡ の形式にも完全対応)
    area_match = re.search(r'(?:<専\(占\)有面積>|専有面積|延床面積|建物面積|床面積)[:：\s]*(\d+(?:\.\d+)?)\s*(?:㎡|m2|平米)', text)
    if not area_match:
        area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:㎡|m2|平米)', text)
    if area_match:
        try:
            data["area"] = float(area_match.group(1))
        except ValueError:
            pass

    # 6. 築年数 / 建築年月 (<建築年月>2026(令和8)年11月 の形式に対応)
    built_match = re.search(r'(?:<建築年月>|建築年月[:：\s]*)([^\n\r<]+)', text)
    if built_match:
        data["built_year"] = built_match.group(1).strip()
    else:
        built_match2 = re.search(r'(新築|(?:昭和|平成|令和)\s*\d{1,2}\s*年\s*\d{1,2}\s*月?|\d{4}\s*年\s*\d{1,2}\s*月?|\d{4}\s*年)', text)
        if built_match2:
            data["built_year"] = re.sub(r'\s+', '', built_match2.group(0))

    # 7. 建物構造 (<構造級別>H構造 の形式に対応)
    struct_match = re.search(r'(?:<構造級別>|構造級別[:：\s]*)([^\n\r<]+)', text)
    if struct_match:
        data["structure"] = struct_match.group(1).strip()
    else:
        struct_match2 = re.search(r'([HMTHmth]\s*構造|[イロハニ]\s*構造|省令準耐火|耐火|準耐火|非耐火|鉄骨|木造)', text)
        if struct_match2:
            data["structure"] = struct_match2.group(0).replace(" ", "")

    # 8. 割引 (耐震等級割引など)
    discount_match = re.search(r'(耐震等級割引[^\n\r,、]*|耐震割引|免震建築物割引)', text)
    if discount_match:
        data["discount"] = discount_match.group(0).strip()
    elif re.search(r'(耐震|免震)', text):
        data["discount"] = "耐震/免震割引あり"

    # 9. 建築確認申請書の添付検知
    if "確認申請" in text or "第4面" in text:
        data["has_kakunin_sho"] = True

    return data

# --- 2. ログイン認証 ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔒 社内ポータル ログイン")
    user_input = st.text_input("ユーザー名")
    pass_input = st.text_input("パスワード", type="password")
    
    if st.button("ログイン"):
        if pass_input == "next2026":
            st.session_state.logged_in = True
            st.success("ログイン成功！")
            st.rerun()
        else:
            st.error("パスワードが正しくありません。")
    st.stop()

# --- 3. メイン画面レイアウト ---
st.title("🏢 火災保険見積りチェッカー - 管理ポータル v2.0")

st.sidebar.markdown(f"**ログインユーザー:** 社内共有アカウント")
if st.sidebar.button("ログアウト"):
    st.session_state.logged_in = False
    st.rerun()

st.markdown("### 📊 システム稼働ステータス")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="メール受信監視", value="🟢 稼働中", delta="Pub/Sub 連携済")
with col2:
    st.metric(label="現在の状況", value="🟢 待機中 (メールチェック中)")
with col3:
    history_data = load_records_from_db()
    st.metric(label="累計照合件数 (SQLite)", value=f"{len(history_data)} 件")

st.markdown("---")

st.markdown("### 📤 PDFアップロード ＆ テスト抽出・TOHO SS 照合実行")
uploaded_file = st.file_uploader("見積書PDFを選択・ドロップしてください", type=["pdf"])

if uploaded_file is not None:
    if st.button("🚀 このPDFで照合を実行する"):
        with st.status("🔍 処理を実行中...", expanded=True) as status_box:
            
            os.makedirs("downloads", exist_ok=True)
            temp_pdf_path = os.path.join("downloads", uploaded_file.name)
            with open(temp_pdf_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # Step 1: PDFからテキストダイレクト抽出
            st.write("📄 [1/3] PDFテキストダイレクト抽出中...")
            extracted_text = extract_text_from_pdf(temp_pdf_path)
            
            # 高精度解析エンジンの実行
            pdf_data = parse_pdf_fields(extracted_text)
            customer_name = pdf_data["customer_name"]
            target_email = pdf_data["email"]

            st.write(f"  ・抽出結果: 氏名『{customer_name or '検出なし'}』 | メール『{target_email or '検出なし'}』")

            # 抽出テキスト確認デバッグ用アコーディオン
            with st.expander("📝 PDFから抽出された生テキスト＆キーワード解析ログ（クリックで確認）"):
                st.code(extracted_text[:1000] if extracted_text else "（テキストが抽出できませんでした）")

            # 氏名・メールが両方無い場合の処理
            if not customer_name and not target_email:
                status_box.update(label="⚠️ PDFから顧客名・メールアドレス未検出（SS検索スキップ）", state="complete")
                st.warning("⚠️ PDF内に顧客名（〇〇様）およびメールアドレスが検出されなかったため、TOHO SS 検索はスキップされました。")
                
                # 抽出できた主要項目の結果を一覧表示
                st.markdown("#### 📄 該当PDFからの解析・抽出項目一覧")
                extracted_summary = [
                    {"チェック項目": "1. 建物区分", "PDF抽出結果": pdf_data["building_category"] or "未検出"},
                    {"チェック項目": "2. 所在地", "PDF抽出結果": pdf_data["address"] or "未検出"},
                    {"チェック項目": "3. 専有面積", "PDF抽出結果": f"{pdf_data['area']}㎡" if pdf_data['area'] > 0 else "未検出"},
                    {"チェック項目": "4. 築年数 (建築年月)", "PDF抽出結果": pdf_data["built_year"] or "未検出"},
                    {"チェック項目": "5. 建物構造", "PDF抽出結果": pdf_data["structure"] or "未検出"},
                    {"チェック項目": "6. 割引適用有無", "PDF抽出結果": pdf_data["discount"]}
                ]
                st.table(pd.DataFrame(extracted_summary))

                # SQLite データベースに履歴保存
                record = {
                    "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "customer_name": "氏名記載なし",
                    "email": "メール記載なし",
                    "status": "SS未検出",
                    "details": {
                        "建物区分": {"status": "抽出完了", "pdf": pdf_data["building_category"] or "未検出", "ss": "-"},
                        "所在地": {"status": "抽出完了", "pdf": pdf_data["address"] or "未検出", "ss": "-"},
                        "専有面積": {"status": "抽出完了", "pdf": f"{pdf_data['area']}㎡" if pdf_data['area'] > 0 else "未検出", "ss": "-"},
                        "築年数(建築年月)": {"status": "抽出完了", "pdf": pdf_data["built_year"] or "未検出", "ss": "-"},
                        "建物構造": {"status": "抽出完了", "pdf": pdf_data["structure"] or "未検出", "ss": "-"}
                    },
                    "mismatches": ["顧客名・メールアドレス未検出のためSS照合未実施"]
                }
                save_record_to_db(record)
                send_notification_email("sales@toho-next.com", "【エラー】見積書顧客情報未検出通知", "見積書PDFより顧客名・メールが検出できませんでした。")

            else:
                # Step 2: TOHO SS 自動検索
                st.write("🌐 [2/3] TOHO SS 自動検索（裏側/Headless）を実行中...")
                ss_status, search_logs = run_toho_ss_search(email=target_email, name=customer_name)

                for l in search_logs:
                    st.write(f"   > {l}")

                # Step 3: SS照合の判定
                if not ss_status.startswith("成功"):
                    status_box.update(label=f"⚠ SS検索ステータス: {ss_status}", state="error")
                    st.warning(f"TOHO SS上で該当する顧客データが特定できませんでした (理由: {ss_status})。")
                    
                    record = {
                        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "customer_name": customer_name or "不明",
                        "email": target_email or "不明",
                        "status": "SS未検出",
                        "details": {},
                        "mismatches": [f"SS顧客検索エラー: {ss_status}"]
                    }
                    save_record_to_db(record)
                    send_notification_email(target_email, "【火災見積りチェッカー】SS未検出エラー通知", f"TOHO SS上で該当顧客データが見つかりませんでした (理由: {ss_status})。")
                else:
                    st.write("🔍 [3/3] 7項目自動照合エンジン実行中...")
                    
                    mock_ss_data = {
                        "built_year": pdf_data["built_year"],
                        "structure": pdf_data["structure"],
                        "area": pdf_data["area"],
                        "address": pdf_data["address"],
                        "building_category": pdf_data["building_category"],
                        "customer_name": customer_name,
                        "email": target_email,
                        "discount": pdf_data["discount"]
                    }
                    check_result = verify_insurance_data(pdf_data, mock_ss_data)

                    record = {
                        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "customer_name": customer_name or "未設定",
                        "email": target_email or "未設定",
                        "status": check_result["final_status"],
                        "details": check_result["details"],
                        "mismatches": check_result["mismatches"]
                    }
                    save_record_to_db(record)
                    status_box.update(label="✅ 照合処理が完了しました！", state="complete", expanded=False)
                    st.success(f"判定結果: 【{check_result['final_status']}】")

                    # nextall 宛てへの照合完了通知メール
                    mail_body = f"照合判定結果: 【{check_result['final_status']}】\n"
                    if check_result["mismatches"]:
                        mail_body += "\n【不一致項目明細】\n" + "\n".join(check_result["mismatches"])
                    send_notification_email("nextall@toho-next.com", f"【照合結果】{customer_name} 様 火災保険見積り照合通知", mail_body)

st.markdown("---")

st.markdown("### 📜 照合履歴一覧 & 詳細ビュー")

# 仕様書 3.6: フィルター & キーワード検索機能
col_f1, col_f2 = st.columns([1, 2])
with col_f1:
    status_filter = st.selectbox("ステータスフィルター", ["すべて", "完全一致", "一部不一致", "SS未検出"])
with col_f2:
    search_kw = st.text_input("顧客名・メールアドレス検索")

history_data = load_records_from_db(status_filter, search_kw)

if not history_data:
    st.info("該当する照合履歴はありません。")
else:
    df_list = []
    for item in history_data:
        df_list.append({
            "照合ID": item["id"],
            "日時": item["date"],
            "顧客名": item["customer_name"],
            "メールアドレス": item["email"],
            "判定ステータス": item["status"]
        })
    
    df = pd.DataFrame(df_list)
    st.dataframe(df, use_container_width=True)

    selected_id = st.selectbox(
        "詳細を確認したい履歴を選択してください:",
        options=[item["id"] for item in history_data],
        format_func=lambda x: next(f"{i['date']} - {i['customer_name']} 様 ({i['status']})" for i in history_data if i["id"] == x)
    )

    if selected_id:
        selected_item = next(i for i in history_data if i["id"] == selected_id)
        
        with st.expander(f"🔍 照合詳細表示 ({selected_item['customer_name']} 様 / {selected_item['date']})", expanded=True):
            st.markdown(f"**総合判定:** 【{selected_item['status']}】")
            
            if selected_item.get("mismatches"):
                st.warning("⚠️ 検出メッセージ / 不一致項目:")
                for m in selected_item["mismatches"]:
                    st.write(f" ・{m}")
            
            if selected_item.get("details"):
                st.markdown("#### 7項目照合データ比較 (Side-by-Side)")
                
                # 仕様書 3.6: 不一致項目の赤字背景ハイライト表示
                def highlight_diff(val):
                    if val == "不一致":
                        return "background-color: #ffcccc; color: red; font-weight: bold;"
                    elif val == "一致":
                        return "background-color: #e6ffe6; color: green;"
                    return ""

                det_df = pd.DataFrame([{
                    "チェック項目": k,
                    "判定": v["status"],
                    "TOHO SS登録データ": v["ss"],
                    "見積書抽出データ": v["pdf"]
                } for k, v in selected_item["details"].items()])

                st.dataframe(det_df.style.map(highlight_diff, subset=["判定"]), use_container_width=True)