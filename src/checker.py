import re

def normalize_text(text: str) -> str:
    """文字列の表記揺れ（全角・半角・スペース）を正規化する"""
    if not text:
        return ""
    # 全角数字・英字を半角に変換
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    # スペース除去
    text = re.sub(r'\s+', '', text)
    return text

def check_area_diff(pdf_area: float, ss_area: float, tolerance: float = 1.0) -> bool:
    """専有面積の誤差判定 (許容誤差 ±1.0m² 以内)"""
    try:
        return abs(float(pdf_area) - float(ss_area)) <= tolerance
    except (ValueError, TypeError):
        return False

def verify_insurance_data(pdf_data: dict, ss_data: dict) -> dict:
    """
    仕様書 3.2 に基づく 7項目の自動照合・判定エンジン
    """
    results = {}
    mismatches = []

    # 1. 建築年月
    pdf_built = normalize_text(pdf_data.get("built_year", ""))
    ss_built = normalize_text(ss_data.get("built_year", ""))
    built_ok = (pdf_built in ss_built) or (ss_built in pdf_built) if (pdf_built and ss_built) else False
    results["1_建築年月"] = {"status": "OK" if built_ok else "差分あり", "pdf": pdf_built, "ss": ss_built}
    if not built_ok:
        mismatches.append(f"建築年月不一致 (PDF: {pdf_built} / SS: {ss_built})")

    # 2. 建物区分 / 構造
    pdf_struct = normalize_text(pdf_data.get("structure", ""))
    ss_struct = normalize_text(ss_data.get("structure", ""))
    struct_ok = (pdf_struct in ss_struct) or (ss_struct in pdf_struct) if (pdf_struct and ss_struct) else False
    results["2_建物区分_構造"] = {"status": "OK" if struct_ok else "差分あり", "pdf": pdf_struct, "ss": ss_struct}
    if not struct_ok:
        mismatches.append(f"建物構造不一致 (PDF: {pdf_struct} / SS: {ss_struct})")

    # 3. 専有面積 (±1.0m² 許容)
    pdf_area = pdf_data.get("area", 0.0)
    ss_area = ss_data.get("area", 0.0)
    area_ok = check_area_diff(pdf_area, ss_area)
    results["3_専有面積"] = {"status": "OK" if area_ok else "差分あり", "pdf": f"{pdf_area}㎡", "ss": f"{ss_area}㎡"}
    if not area_ok:
        mismatches.append(f"専有面積不一致 (PDF: {pdf_area}㎡ / SS: {ss_area}㎡)")

    # 4. 所在地
    pdf_addr = normalize_text(pdf_data.get("address", ""))
    ss_addr = normalize_text(ss_data.get("address", ""))
    addr_ok = (pdf_addr in ss_addr) or (ss_addr in pdf_addr) if (pdf_addr and ss_addr) else False
    results["4_所在地"] = {"status": "OK" if addr_ok else "差分あり", "pdf": pdf_addr, "ss": ss_addr}
    if not addr_ok:
        mismatches.append(f"所在地不一致 (PDF: {pdf_addr} / SS: {ss_addr})")

    # 5. 顧客氏名
    pdf_name = normalize_text(pdf_data.get("customer_name", ""))
    ss_name = normalize_text(ss_data.get("customer_name", ""))
    name_ok = (pdf_name == ss_name) if (pdf_name and ss_name) else False
    results["5_顧客氏名"] = {"status": "OK" if name_ok else "差分あり", "pdf": pdf_name, "ss": ss_name}
    if not name_ok:
        mismatches.append(f"顧客氏名不一致 (PDF: {pdf_name} / SS: {ss_name})")

    # 6. 送信元メールアドレス
    pdf_email = pdf_data.get("email", "").strip().lower()
    ss_email = ss_data.get("email", "").strip().lower()
    email_ok = (pdf_email == ss_email) if (pdf_email and ss_email) else False
    results["6_送信元メール"] = {"status": "OK" if email_ok else "差分あり", "pdf": pdf_email, "ss": ss_email}
    if not email_ok:
        mismatches.append(f"送信元メール不一致 (PDF: {pdf_email} / SS: {ss_email})")

    # 7. 割引適用有無
    pdf_discount = pdf_data.get("discount", "なし")
    ss_discount = ss_data.get("discount", "なし")
    discount_ok = (pdf_discount == ss_discount)
    results["7_割引適用有無"] = {"status": "OK" if discount_ok else "差分あり", "pdf": pdf_discount, "ss": ss_discount}
    if not discount_ok:
        mismatches.append(f"割引適用不一致 (PDF: {pdf_discount} / SS: {ss_discount})")

    # 全体ステータス判定
    is_perfect_match = len(mismatches) == 0
    final_status = "完全一致" if is_perfect_match else "差分検出あり"

    return {
        "final_status": final_status,
        "is_perfect_match": is_perfect_match,
        "mismatches": mismatches,
        "details": results
    }