#!/bin/bash
SERVICE=""
DRY_RUN=0

# Vòng lặp bóc tách tham số (Argument Parsing)
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --service) SERVICE="$2"; shift ;;
        --dry-run) DRY_RUN=1 ;;
        *) echo "Tham số không hợp lệ: $1"; exit 1 ;;
    esac
    shift
done

if [ -z "$SERVICE" ]; then
    echo "LỖI: Thiếu tham số --service"
    exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[DRY-RUN] OS sẽ chạy lệnh: docker restart $SERVICE"
    exit 0
fi

echo "[ACT] Đang khởi động lại dịch vụ: $SERVICE..."
# Lệnh thật sẽ là: docker restart $SERVICE. Nhưng trong Lab ta giả lập.
sleep 3 
echo "[ACT] Khởi động lại thành công!"
exit 0
