#!/usr/bin/env python3
"""Script test traces với từng prompt label"""
import requests
import time
import os

def send_chat_request(message: str, label: str):
    """Gửi request với label cụ thể"""
    url = "http://127.0.0.1:8000/chat"
    headers = {"Content-Type": "application/json"}
    data = {
        "message": message,
        "session_id": f"test-{label}",
        "user_id": "test-user"
    }

    print(f"\n=== Testing with label: {label} ===")
    print(f"Request: {data}")

    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {result}")
            return result
        else:
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def main():
    test_message = "What is your refund policy?"

    # Test 1: với production label
    print("\n" + "="*50)
    print("TEST 1: Gửi request với LANGFUSE_PROMPT_LABEL=production")
    print("="*50)
    result1 = send_chat_request(test_message, "production")

    if result1:
        print(f"\n✅ Trace created with production label")
        print(f"   Correlation ID: {result1.get('correlation_id', 'N/A')}")

    print("\nĐợi 2 giây...")
    time.sleep(2)

    # Test 2: với candidate label
    print("\n" + "="*50)
    print("TEST 2: Gửi request với LANGFUSE_PROMPT_LABEL=candidate")
    print("="*50)
    result2 = send_chat_request(test_message, "candidate")

    if result2:
        print(f"\n✅ Trace created with candidate label")
        print(f"   Correlation ID: {result2.get('correlation_id', 'N/A')}")

    print("\n" + "="*50)
    print("HOÀN THÀNH!")
    print("="*50)
    print("\nBây giờ vào Langfuse Dashboard:")
    print("1. Filter: tags:day13")
    print("2. Sẽ thấy 2 traces: 1 với prompt_label=production, 1 với prompt_label=candidate")

if __name__ == "__main__":
    main()
