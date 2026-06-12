import os
import glob
import subprocess

def run_all():
    # 1. Tìm tất cả các file sự cố (có tên bắt đầu bằng chữ E, đuôi .json) trong thư mục eval
    eval_files = glob.glob("eval/E*.json")
    
    # 2. Xóa file chấm điểm cũ (nếu có) để tránh việc ghi đè lộn xộn từ lần chạy trước
    if os.path.exists("audit.jsonl"):
        os.remove("audit.jsonl")
        print("Đã xóa file audit.jsonl cũ.")
        
    # 3. Lặp qua từng file sự cố tìm được (từ E01 đến E08)
    for file in sorted(eval_files):
        print(f"Đang xử lý: {file}")
        
        # Tạo ra câu lệnh Terminal y hệt như cách bạn gõ tay
        cmd = [
            "python", "engine.py", "decide",
            "--incident", file,
            "--history", "incidents_history.json",
            "--actions", "actions.yaml"
        ]
        
        # 4. Giao lệnh cho Windows chạy và đợi nó chạy xong
        subprocess.run(cmd, check=True)
        
    # 5. In ra câu chúc mừng sau khi lặp xong cả 8 file
    print("\nĐã xử lý xong tất cả các file. Bây giờ bạn có thể chạy:")
    print("python grade.py --audit audit.jsonl --expected eval/expected.json")

if __name__ == "__main__":
    run_all()
