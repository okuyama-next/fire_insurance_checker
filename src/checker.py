import re

def normalize_text(text: str) -> str:
    """スペース除去および全半角統一"""
    if not text:
        return ""
    text = re.sub(r'\s+', '', str(text))
    # 全角英数を半角化
    return text.translate(str.maketrans(
        '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    ))

def convert_to_seireki(year_str: str) -> str:
    """和暦(令和・平成・昭和)と西暦の相互変換吸収"""
    if not year_str:
        return ""
    year_str = normalize_text(year_str)
    
    # 令和
    m = re.search(r'令和(\d+)年?(\d+)?月?', year_str)
    if m:
        y = 2018 + int(m.group(1))
        mon = m.group(2) or "1"
        return f"{y}年{mon}月"
    # 平成
    m = re.search(r'平成(\d+)年?(\d+)?月?', year_str)
    if m:
        y = 1988 + int(m.group(1))
        mon = m.group(2) or "1"
        return f"{y}年{mon}月"
    # 昭和
    m = re.search(r'昭和(\d+)年?(\d+)?月?', year_str)
    if m:
        y = 1925 + int(m.group(1))
        mon = m.group(2) or "1"
        return f"{y}年{mon}月"
    return year_str

def verify_insurance_data(pdf_data: dict, ss_data: dict) -> dict:
    """
    仕様書 3.4 に基づく 7 項目自動照合エンジン
    """
    mismatches = []
    details = {}
    
    # 1. 顧客名 (スペース除去・全半角統一)
    p_name = normalize_text(pdf_data.get("customer_name", ""))
    s_name = normalize_text(ss_data.get("customer_name", ""))
    if p_name == s_name and p_name != "":
        details["顧客名"] = {"status": "一致", "pdf": pdf_data.get("customer_name"), "ss": ss_data.get("customer_name")}
    else:
        mismatches.append(f"顧客名不一致 (SS: {ss_data.get('customer_name')} / 見積書: {pdf_data.get('customer_name')})")
        details["顧客名"] = {"status": "不一致", "pdf": pdf_data.get("customer_name"), "ss": ss_data.get("customer_name")}

    # 2. メールアドレス (小文字統一)
    p_mail = (pdf_data.get("email") or "").lower().strip()
    s_mail = (ss_data.get("email") or "").lower().strip()
    if p_mail == s_mail and p_mail != "":
        details["メールアドレス"] = {"status": "一致", "pdf": p_mail, "ss": s_mail}
    else:
        mismatches.append(f"メールアドレス不一致 (SS: {s_mail} / 見積書: {p_mail})")
        details["メールアドレス"] = {"status": "不一致", "pdf": p_mail, "ss": s_mail}

    # 3. 建物区分 (戸建て / マンション)
    p_cat = pdf_data.get("building_category", "")
    s_cat = ss_data.get("building_category", "戸建て")
    if ("戸建" in p_cat and "戸建" in s_cat) or ("マンション" in p_cat and "マンション" in s_cat):
        details["建物区分"] = {"status": "一致", "pdf": p_cat, "ss": s_cat}
    else:
        mismatches.append(f"建物区分不一致 (SS: {s_cat} / 見積書: {p_cat})")
        details["建物区分"] = {"status": "不一致", "pdf": p_cat, "ss": s_cat}

    # 4. 物件所在地 (都道府県・市区町村正規化)
    p_addr = normalize_text(pdf_data.get("address", ""))
    s_addr = normalize_text(ss_data.get("address", ""))
    if p_addr in s_addr or s_addr in p_addr:
        details["物件所在地"] = {"status": "一致", "pdf": pdf_data.get("address"), "ss": ss_data.get("address")}
    else:
        mismatches.append(f"物件所在地不一致 (SS: {ss_data.get('address')} / 見積書: {pdf_data.get('address')})")
        details["物件所在地"] = {"status": "不一致", "pdf": pdf_data.get("address"), "ss": ss_data.get("address")}

    # 5. 専有面積 (数値比較)
    p_area = float(pdf_data.get("area", 0.0))
    s_area = float(ss_data.get("area", 0.0))
    if abs(p_area - s_area) < 1.0:
        details["専有面積"] = {"status": "一致", "pdf": f"{p_area}㎡", "ss": f"{s_area}㎡"}
    else:
        mismatches.append(f"専有面積不一致 (SS: {s_area}㎡ / 見積書: {p_area}㎡)")
        details["専有面積"] = {"status": "不一致", "pdf": f"{p_area}㎡", "ss": f"{s_area}㎡"}

    # 6. 築年数 (和暦/西暦自動変換)
    p_built = convert_to_seireki(pdf_data.get("built_year", ""))
    s_built = convert_to_seireki(ss_data.get("built_year", ""))
    if p_built == s_built or (p_built and p_built in s_built):
        details["築年数"] = {"status": "一致", "pdf": pdf_data.get("built_year"), "ss": ss_data.get("built_year")}
    else:
        mismatches.append(f"築年数不一致 (SS: {ss_data.get('built_year')} / 見積書: {pdf_data.get('built_year')})")
        details["築年数"] = {"status": "不一致", "pdf": pdf_data.get("built_year"), "ss": ss_data.get("built_year")}

    # 7. 建物構造 (仕様書 3.4 建築確認申請書特記対応)
    p_struct = pdf_data.get("structure", "")
    s_struct = ss_data.get("structure", "")
    has_kakunin = pdf_data.get("has_kakunin_sho", False)
    
    if "戸建" in p_cat:
        if has_kakunin:
            note = "【建築確認申請書添付あり】第4面OCR取得済み"
        else:
            note = "【注記】建築確認申請書は見つかりませんでした"
    else:
        note = "マンション（鉄筋コンクリート等）"

    if p_struct and p_struct in s_struct:
        details["建物構造"] = {"status": "一致", "pdf": f"{p_struct} ({note})", "ss": s_struct}
    else:
        mismatches.append(f"建物構造不一致 (SS: {s_struct} / 見積書: {p_struct})")
        details["建物構造"] = {"status": "不一致", "pdf": f"{p_struct} ({note})", "ss": s_struct}

    final_status = "完全一致" if not mismatches else "一部不一致"
    return {
        "final_status": final_status,
        "details": details,
        "mismatches": mismatches
    }