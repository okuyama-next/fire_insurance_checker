import os
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/pubsub'
]

def get_gmail_service():
    """OAuth2認証を行ってGmail APIサービスを取得"""
    token_path = 'credentials/token.json'
    if not os.path.exists(token_path):
        raise FileNotFoundError("credentials/token.json が見つかりません。")
    
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build('gmail', 'v1', credentials=creds)

def fetch_latest_message():
    """受信トレイから最新のメール1件を取得"""
    service = get_gmail_service()
    
    # 受信トレイ(INBOX)の最新メールIDを取得
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
    messages = results.get('messages', [])
    
    if not messages:
        print("受信トレイにメールが見つかりませんでした。")
        return None

    msg_id = messages[0]['id']
    # メール詳細データの取得
    message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    return message

def parse_and_save_email(message, output_dir='downloads'):
    """メール本文と添付PDFを取得して保存"""
    service = get_gmail_service()
    msg_id = message['id']
    payload = message.get('payload', {})
    headers = payload.get('headers', [])
    
    # ヘッダー情報の取得
    subject = ""
    sender = ""
    for header in headers:
        if header['name'].lower() == 'subject':
            subject = header['value']
        elif header['name'].lower() == 'from':
            sender = header['value']
            
    print("----------------------------------------")
    print(f"【メール情報取得】")
    print(f"・Message ID: {msg_id}")
    print(f"・送信者 (From): {sender}")
    print(f"・件名 (Subject): {subject}")
    print("----------------------------------------")

    # 添付ファイルの抽出処理
    parts = payload.get('parts', [])
    downloaded_files = []

    def process_parts(parts_list):
        for part in parts_list:
            filename = part.get('filename')
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')

            # PDF添付ファイルが存在する場合
            if filename and filename.lower().endswith('.pdf') and attachment_id:
                attachment = service.users().messages().attachments().get(
                    userId='me', messageId=msg_id, id=attachment_id
                ).execute()
                
                file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
                
                os.makedirs(output_dir, exist_ok=True)
                file_path = os.path.join(output_dir, filename)
                
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                
                print(f"★ 添付PDFを保存しました: {file_path}")
                downloaded_files.append(file_path)

            # ネストされたパーツ（マルチパートメール等）の再帰処理
            if 'parts' in part:
                process_parts(part['parts'])

    if parts:
        process_parts(parts)
    else:
        # パーツがない単一メッセージの場合の処理
        filename = payload.get('filename')
        if filename and filename.lower().endswith('.pdf'):
            body = payload.get('body', {})
            attachment_id = body.get('attachmentId')
            if attachment_id:
                attachment = service.users().messages().attachments().get(
                    userId='me', messageId=msg_id, id=attachment_id
                ).execute()
                file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
                os.makedirs(output_dir, exist_ok=True)
                file_path = os.path.join(output_dir, filename)
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                print(f"★ 添付PDFを保存しました: {file_path}")
                downloaded_files.append(file_path)

    return {
        'msg_id': msg_id,
        'sender': sender,
        'subject': subject,
        'pdf_paths': downloaded_files
    }

if __name__ == '__main__':
    # 単体テスト実行
    print("最新メールの取得テストを開始します...")
    msg = fetch_latest_message()
    if msg:
        result = parse_and_save_email(msg)
        print("\n[取得完了結果]")
        print(result)