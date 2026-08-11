import os
import time
import requests
from dotenv import load_dotenv
from langfuse import Langfuse

def main():
    load_dotenv()
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if not public_key or not secret_key:
        print("Vui lòng cấu hình LANGFUSE_PUBLIC_KEY và LANGFUSE_SECRET_KEY trong file .env trước khi chạy script.")
        return

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    # 1. Tạo version 1, gắn labels baseline và production
    prompt_template_v1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
    print("Đang tạo Prompt Version 1...")
    prompt_v1 = client.create_prompt(
        name="day13-chat",
        type="text",
        prompt=prompt_template_v1,
        labels=["baseline", "production"]
    )
    time.sleep(2)
    
    # 2. Tạo version 2 với một thay đổi nhỏ, gắn label candidate
    prompt_template_v2 = "Feature={{feature}}\nDocs={{docs}}\nUser Question={{message}}"
    print("Đang tạo Prompt Version 2...")
    prompt_v2 = client.create_prompt(
        name="day13-chat",
        type="text",
        prompt=prompt_template_v2,
        labels=["candidate"]
    )
    time.sleep(2)
    
    # Hàm gọi API chat
    def call_chat_api(label):
        url = "http://127.0.0.1:8000/chat"
        headers = {"Content-Type": "application/json"}
        # Cập nhật môi trường cho process hiện tại (không ảnh hưởng API server nếu API server đã chạy,
        # nên API server phải được restart hoặc đọc env cho từng request.
        # Trong code lab, resolve_prompt() đọc os.getenv("LANGFUSE_PROMPT_LABEL") 
        # nên việc đổi env ở script này không có tác dụng với API server đang chạy.
        # Thay vào đó, API server gọi Langfuse. Ở đây chỉ trigger load test.
        # Thực ra, theo hướng dẫn: "Chạy cùng một input với LANGFUSE_PROMPT_LABEL=baseline và candidate."
        # Nên cần đổi env của API server. Do đó, người dùng cần restart API.
        pass

    print("\n--- HOÀN THÀNH TẠO PROMPT VERSION TRÊN LANGFUSE ---")
    print(f"Version 1 ID: {prompt_v1.id if hasattr(prompt_v1, 'id') else 'V1'}")
    print(f"Version 2 ID: {prompt_v2.id if hasattr(prompt_v2, 'id') else 'V2'}")
    print("\nCác bước tiếp theo (do cần khởi động lại API server với env khác nhau):")
    print("1. Đặt LANGFUSE_PROMPT_LABEL=baseline trong .env, khởi động lại API, dùng Postman hoặc load test gửi 1 request. Lấy Trace ID ghi vào REPORT.md")
    print("2. Đặt LANGFUSE_PROMPT_LABEL=candidate trong .env, khởi động lại API, gửi 1 request. Lấy Trace ID ghi vào REPORT.md")
    print("3. Trên Langfuse UI, chuyển label 'production' sang Version 2, chụp ảnh màn hình.")
    print("4. Đặt LANGFUSE_PROMPT_LABEL=production trong .env, khởi động lại API, gửi 1 request.")
    print("5. Trên Langfuse UI, rollback label 'production' về Version 1, chụp ảnh màn hình làm evidence.")

if __name__ == "__main__":
    main()
