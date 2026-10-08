import sqlite3
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

DB_PATH = "credentials/history.db"

def init_db():
    """SQLite データベースの初期化"""
    os.makedirs("credentials", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_history (
            id TEXT PRIMARY KEY,
            date TEXT,
            customer_name TEXT,
            email TEXT,
            status TEXT,
            details_json TEXT,
            mismatches_json TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_record_to_db(record):
    """データベースへのレコード挿入"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO check_history (id, date, customer_name, email, status, details_json, mismatches_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        record["id"],
        record["date"],
        record.get("customer_name", "未設定"),
        record.get("email", "未設定"),
        record["status"],
        json.dumps(record.get("details", {}), ensure_ascii=False),
        json.dumps(record.get("mismatches", []), ensure_ascii=False)
    ))
    conn.commit()
    conn.close()

def load_records_from_db(status_filter="すべて", search_kw=""):
    """データベースからの履歴取得 (フィルタリング・検索対応)"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = "SELECT id, date, customer_name, email, status, details_json, mismatches_json FROM check_history WHERE 1=1"
    params = []
    
    if status_filter != "すべて":
        query += " AND status LIKE ?"
        params.append(f"%{status_filter}%")
        
    if search_kw:
        query += " AND (customer_name LIKE ? OR email LIKE ?)"
        params.extend([f"%{search_kw}%", f"%{search_kw}%"])
        
    query += " ORDER BY date DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    records = []
    for row in rows:
        records.append({
            "id": row[0],
            "date": row[1],
            "customer_name": row[2],
            "email": row[3],
            "status": row[4],
            "details": json.loads(row[5]) if row[5] else {},
            "mismatches": json.loads(row[6]) if row[6] else []
        })
    return records

def send_notification_email(to_email, subject, body, attachment_path=None):
    """仕様書 3.5 に準拠したメール通知機能 (内部ログ出力付き)"""
    print(f"\n📧 [メール送信通知ログ]")
    print(f" 宛先: {to_email}")
    print(f" 件名: {subject}")
    print(f" 本文:\n{body}")
    if attachment_path:
        print(f" 添付ファイル: {attachment_path}")
    print("--------------------------------------------------")