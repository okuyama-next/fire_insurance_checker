import pdfplumber
import os
import glob

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    pdfplumberを使用してPDF内の埋め込みテキストを抽出する関数（AI・OCR不使用）
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")

    full_text = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text:
                full_text.append(f"--- Page {page_num} ---\n{text}")
                
    return "\n\n".join(full_text)

def get_latest_pdf(download_dir='downloads'):
    """downloads フォルダ内の最新のPDFファイルパスを取得"""
    pdf_files = glob.glob(os.path.join(download_dir, '*.pdf'))
    if not pdf_files:
        return None
    # 更新日時が最新のファイルを取得
    latest_file = max(pdf_files, key=os.path.getmtime)
    return latest_file

if __name__ == '__main__':
    latest_pdf = get_latest_pdf()
    
    if not latest_pdf:
        print("downloads フォルダ内にPDFファイルが見つかりません。")
    else:
        print("----------------------------------------")
        print(f"PDFテキスト抽出テスト開始: {latest_pdf}")
        print("----------------------------------------")
        
        try:
            extracted_text = extract_text_from_pdf(latest_pdf)
            print("【抽出テキスト結果】")
            print(extracted_text)
            print("----------------------------------------")
            print("★ テキスト抽出に成功しました！")
        except Exception as e:
            print(f"エラーが発生しました: {e}")