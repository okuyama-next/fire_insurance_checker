import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Gmail と Pub/Sub のアクセス権限スコープ
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/pubsub'  # <-- Pub/Sub権限を追加
]

def get_gmail_service():
    """OAuth2認証を行ってGmail APIサービスを取得"""
    creds = None
    token_path = 'credentials/token.json'
    client_secret_path = 'credentials/client_secret.json'

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def set_gmail_watch(project_id: str, topic_name: str):
    """GmailにWatch（監視）リクエストを送信"""
    service = get_gmail_service()
    
    request_body = {
        'topicName': f'projects/{project_id}/topics/{topic_name}',
        'labelIds': ['INBOX']
    }
    
    response = service.users().watch(userId='me', body=request_body).execute()
    print("----------------------------------------")
    print("【成功】Gmail Watch（監視設定）が正常に登録されました！")
    print(f"有効期限 (Expiration): {response.get('expiration')}")
    print(f"History ID: {response.get('historyId')}")
    print("----------------------------------------")

if __name__ == '__main__':
    PROJECT_ID = 'kasaichecker'
    TOPIC_NAME = 'gmail-notifications'
    
    set_gmail_watch(PROJECT_ID, TOPIC_NAME)