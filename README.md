# ⚽ Football Vote Bot (Telegram)

Bot Telegram tự động quản lý vote đá bóng hàng tuần cho nhóm.

## Tính năng

- **Tự động tạo vote** thứ 6 lúc 8:30 sáng mỗi tuần
- **Tự động nhắc nhở** thứ 2 lúc 8:30 sáng — tag người chưa vote
- **Tự động đóng vote** thứ 2 lúc 12:00 trưa
- **Auto-pin** tin nhắn vote
- **Theo dõi vote** real-time (ai đá, ai không đá, ai chưa vote)
- **Phát hiện inactive** — ai vote "Không đá" 3 tuần liên tiếp

## Lệnh Bot

| Lệnh | Mô tả |
|-------|--------|
| `/register` | Đăng ký vào nhóm đá bóng |
| `/list` hoặc `/ds` | Xem danh sách vote hiện tại |
| `/inactive` hoặc `/vang` | Xem người 3 tuần liên tiếp vote không đá |
| `/help` | Hiển thị trợ giúp |
| `/testpoll` | (Dev) Tạo poll test thủ công |

## Cài đặt

### Yêu cầu
- Docker & Docker Compose
- Telegram Bot Token (tạo qua [@BotFather](https://t.me/BotFather))

### Bước 1: Tạo Bot
1. Chat với [@BotFather](https://t.me/BotFather) trên Telegram
2. Gửi `/newbot` và làm theo hướng dẫn
3. Copy **Bot Token** được cung cấp

### Bước 2: Thêm Bot vào Group
1. Thêm bot vào group Telegram
2. **Đặt bot làm admin** với quyền:
   - Gửi tin nhắn (Send messages)
   - Ghim tin nhắn (Pin messages)

### Bước 3: Lấy CHAT_ID
Cách đơn giản nhất:
1. Thêm bot [@userinfobot](https://t.me/userinfobot) vào group
2. Gửi bất kỳ tin nhắn nào trong group
3. Bot sẽ trả về Chat ID (dạng `-100xxxxxxxxxx`)

### Bước 4: Cấu hình
```bash
cp .env.example .env
```
Sửa file `.env`:
```env
BOT_TOKEN=your-bot-token-here
CHAT_ID=-1001234567890
```

### Bước 5: Chạy
```bash
docker compose up -d --build
```

## Vận hành

```bash
# Xem logs
docker compose logs -f bot

# Khởi động lại
docker compose restart bot

# Dừng bot
docker compose down

# Backup dữ liệu
docker compose cp bot:/app/data ./backup-data
```

## Lịch tự động

| Thời gian | Hành động |
|-----------|-----------|
| **Thứ 6, 8:30 sáng** | Tạo poll vote + ghim |
| **Thứ 2, 8:30 sáng** | Nhắc nhở + tag người chưa vote |
| **Thứ 2, 12:00 trưa** | Đóng poll + gửi tổng kết |

## Cấu trúc dự án

```
bot/
├── main.py              # Entry point
├── config.py            # Cấu hình từ env
├── database.py          # SQLite queries
├── utils.py             # Helpers
├── handlers/
│   ├── commands.py      # /register, /list, /inactive, /help
│   └── poll_handler.py  # Xử lý vote real-time
└── scheduler/
    └── jobs.py          # 3 scheduled jobs
```

## Lưu ý

- Bot **phải là admin** trong group để ghim tin nhắn và nhận poll answers
- Bot tự động đăng ký member khi họ gửi tin nhắn hoặc vote
- Dữ liệu lưu trong SQLite, persist qua Docker volume
- Timezone cố định: `Asia/Ho_Chi_Minh` (UTC+7)

## Troubleshooting

| Vấn đề | Giải pháp |
|--------|-----------|
| Bot không pin được | Kiểm tra bot có quyền admin + Pin messages |
| Không nhận vote | Kiểm tra `allowed_updates` include `poll_answer` |
| Sai giờ | Kiểm tra `TZ=Asia/Ho_Chi_Minh` trong docker-compose |
| Bot không phản hồi | `docker compose logs bot` để xem lỗi |
