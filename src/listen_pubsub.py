import json
import os
from google.oauth2.credentials import Credentials
from google.cloud import pubsub_v1

PROJECT_ID = 'kasaichecker'
SUBSCRIPTION_ID = 'gmail-notifications-sub'
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/pubsub'  # <-- Pub/Sub権限を追加
]

def callback(message):
    """Pub/Subにメッセージが届いたときに自動実行される関数"""
    print("\n========================================")
    print("★ [検知] 新しいメールの受信を検知しました！")
    print("========================================")
    
    data_str = message.data.decode("utf-8")
    try:
        payload = json.loads(data_str)
        print(f"・対象メールアドレス: {payload.get('emailAddress')}")
        print(f"・最新 History ID: {payload.get('historyId')}")
    except json.JSONDecodeError:
        print(f"・受信メッセージ: {data_str}")
        
    # 処理完了をPub/Subに通知
    message.ack()

def start_listening():
    """Pub/Subサブスクリプションからの通知待機を開始"""
    token_path = 'credentials/token.json'
    
    if not os.path.exists(token_path):
        print("エラー: credentials/token.json が見つかりません。先に register_watch.py を実行してください。")
        return

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    subscriber = pubsub_v1.SubscriberClient(credentials=creds)
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
    
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    print("----------------------------------------")
    print(f"メール受信の監視を開始しました...")
    print("テストメールを送信して、検知できるか確認してください。")
    print("(終了するには Ctrl + C を押します)")
    print("----------------------------------------")
    
    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        print("\n監視を停止しました。")

if __name__ == '__main__':
    start_listening()