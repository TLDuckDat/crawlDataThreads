# 🛡️ Threads City Bad Data Collector & Toxic Analyzer

Chương trình tự động thu thập (cào dữ liệu) chi tiết bài viết, bình luận trên **Threads** (`threads.net`), phát hiện và phân loại các nội dung chứa **ngôn từ xúc phạm, từ lóng Gen Z, chửi thề, lăng mạ nhân phẩm, phân biệt vùng miền, đe dọa bạo lực, quấy rối và icon/emoji nhạy cảm** bằng tiếng Việt. Hỗ trợ **xuất file CSV chi tiết nhất** chuẩn mã UTF-8-BOM để người dùng tự do lọc và tổng hợp trên Microsoft Excel.

---

## 🌟 Tính Năng Nổi Bật

1. **Thu thập dữ liệu chi tiết nhất & Phân cấp Bình luận con (Nested Replies)**:
   - Cào bài đăng gốc và **toàn bộ cây bình luận: cả bình luận gốc (cấp 1) và bình luận con (trả lời / replies)** theo link bài viết Threads.
   - Tự động nhận diện và click mở rộng các nút: **"Xem câu trả lời"**, **"Xem phản hồi"**, **"Xem thêm câu trả lời"**, **"View replies"** để bung toàn bộ bình luận con bị ẩn.
   - Phân loại rõ ràng:
     - `Loại bình luận`: **Bình luận gốc** hoặc **Bình luận con (Phản hồi)**
     - `Phản hồi cho (@Reply To)`: Tài khoản đang được trả lời
     - `Mã bình luận cha (Parent Comment ID)`: Liên kết trực tiếp tới bình luận gốc cha
   - Thu thập đầy đủ các trường:
     - `Mã bình luận (ID)` & `Mã bài gốc (Post ID)`
     - `Link bài gốc` & `Link bình luận trực tiếp`
     - `Tài khoản tác giả (@Username)`, `Tên hiển thị` & `Link Profile cá nhân`
     - `Nội dung bình luận đầy đủ` (giữ nguyên icon/emoji)
     - `Thời gian đăng` & `Lượt thích (Likes)`
     - `Người được trả lời (Reply To)` & `Ảnh đính kèm (Images)`
     - `Kết quả kiểm duyệt độc hại`, `Điểm số`, `Mức độ nghiêm trọng`
     - `Danh sách từ lóng / từ xúc phạm phát hiện`
     - `Danh sách icon / emoji nhạy cảm bắt gặp`
     - `Nhóm vi phạm` & `Thời gian thu thập`
2. **Xử lý từ lóng, có dấu, không dấu & Icon / Emoji nhạy cảm**:
   - **Có dấu & Không dấu**: Nhận diện triệt để từ lóng dù viết có dấu (`lồn`, `cặc`, `buồi`, `địt mẹ`, `óc chó`) hay không dấu (`lon`, `cac`, `buoi`, `dit me`, `oc cho`, `xam lol`).
   - **Từ lóng Threads / Teencode**: Xử lý biến thể lách chữ (`vcl`, `vkl`, `vl`, `clgt`, `đm`, `dcm`, `djt`, `duma`, `sv`, `bake`, `parky`, `namky`, `3que`, `cali`...).
   - **Phát hiện Icon / Emoji độc hại**: Nhận diện các icon xúc phạm, lăng mạ hoặc bạo lực mạng (`🖕`, `💩`, `🤡`, `🐶`, `🐷`, `🐒`, `🍆`, `🍑`, `🔪`, `☠️`, `⚰️`...).
3. **Phần xuất file CSV chi tiết để người dùng tự tổng hợp**:
   - Tùy chọn xuất: **"Toàn bộ dữ liệu (Chi tiết nhất - Để tự tổng hợp)"** hoặc **"Chỉ dữ liệu vi phạm"**.
   - Chuẩn mã **UTF-8-BOM (`utf-8-sig`)**: Double-click mở trực tiếp bằng Microsoft Excel trên Windows hiển thị tiếng Việt và emoji 100% chuẩn nét, không lỗi font.
   - Tiêu đề các cột bằng tiếng Việt rõ ràng, thuận tiện cho việc tạo bảng Pivot, lọc filter, tính toán thống kê.
   - Hỗ trợ xuất đồng thời ra **Excel (.xlsx có tô màu hàng vi phạm)** và **JSON** cho huấn luyện AI.
4. **Hai giao diện sử dụng linh hoạt**:
   - 🖥️ **Web Dashboard (Streamlit)**: Giao diện trực quan, có tab xuất CSV chuyên dụng kèm xem trước bảng dữ liệu, tab thống kê biểu đồ và quản lý từ điển icon.
   - 💻 **CLI dòng lệnh (`main.py`)**: Lệnh chuyên dụng `export-csv` nhanh gọn.

---

## 📂 Cấu Trúc Dự Án

```
ThuThapBadDataThreads/
├── config/
│   ├── settings.py           # Thiết lập đường dẫn, delay, ngưỡng toxic score
│   └── toxic_keywords.json   # Bộ từ điển từ lóng, có dấu, không dấu & icon
├── data/
│   ├── threads_data.db       # Cơ sở dữ liệu SQLite lưu trữ dữ liệu cào
│   └── exports/              # Thư mục chứa file xuất CSV, Excel, JSON
├── src/
│   ├── crawler/
│   │   ├── browser.py        # Quản lý Selenium WebDriver Headless & Stealth
│   │   ├── parser.py         # JavaScript Extractor DOM Threads (hỗ trợ auto-expand)
│   │   └── threads_crawler.py# Bộ cào chi tiết bài viết, bình luận và tìm kiếm
│   ├── detector/
│   │   ├── categories.py     # Định nghĩa các nhóm độc hại, Icon, Severity
│   │   ├── text_normalizer.py# Chuẩn hóa tiếng Việt, teencode, leetspeak
│   │   └── toxic_engine.py   # Thuật toán phân loại từ lóng & tính điểm Toxic Score
│   ├── database/
│   │   ├── models.py         # Model Post & Comment đầy đủ các trường
│   │   └── db_manager.py     # SQLite manager, auto-migration, get_detailed_export_df
│   ├── exporter/
│   │   └── exporter.py       # Bộ xuất CSV chi tiết (UTF-8-BOM), Excel tô màu, JSON
│   └── utils/
│       └── logger.py         # Hệ thống log màu
├── tests/                    # Bộ kiểm thử tự động (11 unit tests)
├── app_dashboard.py          # Giao diện Web Dashboard (Streamlit)
├── main.py                   # Giao diện dòng lệnh CLI
├── requirements.txt          # Danh sách thư viện phụ thuộc
└── README.md                 # Hướng dẫn sử dụng chi tiết
```

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Khởi chạy Giao diện Web Dashboard (Khuyên dùng)

Mở terminal trong thư mục dự án và chạy:
```bash
python -m streamlit run app_dashboard.py
```
Hoặc dùng lệnh điều phối CLI:
```bash
python main.py dashboard
```
Trình duyệt sẽ mở tại `http://localhost:8501`:
- **🚀 Trung tâm Cào dữ liệu**: Nhập link bài viết hoặc từ khóa drama, cào sâu bình luận với thanh tiến trình trực tiếp.
- **📥 Xuất dữ liệu CSV chi tiết (Tự tổng hợp)**: Xem trước bảng dữ liệu chi tiết, chọn xuất toàn bộ hoặc chỉ dữ liệu vi phạm, tải file CSV về chỉ với 1 click.
- **📋 Dữ liệu & Kiểm duyệt**: Tìm kiếm, lọc bình luận theo mức độ nguy hại.
- **📊 Thống kê & Phân tích**: Biểu đồ các từ lóng vi phạm nhiều nhất, top tài khoản vi phạm.
- **🔍 Kiểm tra văn bản & Icon**: Phân tích tức thì mọi câu văn có dấu, không dấu hoặc emoji.
- **📚 Từ điển Từ lóng & Icon**: Xem và thêm từ khóa, quản lý danh sách icon nhạy cảm.

---

### 2. Sử dụng Giao diện Dòng Lệnh (CLI)

#### Xuất file CSV bình luận phân loại (Xấu luôn / Chưa rõ / Toàn bộ):
- **Chỉ xuất các bình luận được đánh giá là XẤU LUÔN (Rõ ràng):**
  ```bash
  python main.py export-csv --status bad
  ```
- **Chỉ xuất các bình luận CHƯA RÕ (Nghi ngờ / Cần duyệt lại):**
  ```bash
  python main.py export-csv --status ambiguous
  ```
- **Xuất TOÀN BỘ bình luận (Đã phân loại Xấu / Chưa rõ / Sạch để tự tổng hợp trên Excel):**
  ```bash
  python main.py export-csv --status all
  ```
- **Lọc theo loại bình luận:**
  ```bash
  # Chỉ xuất bình luận con (phản hồi / replies)
  python main.py export-csv --status all --type reply

  # Chỉ xuất bình luận gốc (top-level comments)
  python main.py export-csv --status all --type root
  ```
- **Tùy chọn: Nếu muốn xuất KÈM THEO CÁC LINK (Link bài gốc, comment, profile, ID cha), thêm cờ `--links`:**
  ```bash
  python main.py export-csv --status bad --links
  ```

#### Cào bình luận từ một bài viết cụ thể:
- **Cào có số lượng giới hạn:**
  ```bash
  python main.py crawl-post --url "https://www.threads.net/@user/post/..." --max 50
  ```
- **♾️ Cào KHÔNG GIỚI HẠN (Cào toàn bộ bình luận cho tới khi hết bài):**
  ```bash
  python main.py crawl-post --url "https://www.threads.net/@user/post/..." --unlimited
  ```
  *(hoặc `--max 0`)*

#### Cào bài viết theo từ khóa tìm kiếm:
- **Cào có giới hạn:**
  ```bash
  python main.py crawl-search --query "bóc phốt drama" --limit 30
  ```
- **♾️ Cào KHÔNG GIỚI HẠN:**
  ```bash
  python main.py crawl-search --query "bóc phốt drama" --unlimited
  ```

#### Kiểm tra độ độc hại, từ lóng & emoji của một câu:
```bash
python main.py scan-text --text "Thằng bake này ngu như bò cút đi 🖕 🤡"
```

#### Xem thống kê dữ liệu đã cào:
```bash
python main.py stats
```

---

## 🧪 Kiểm Thử Tự Động (Unit Tests)

Chạy bộ 14 bài kiểm thử toàn diện (kiểm tra từ lóng có dấu/không dấu, emoji độc hại, chế độ truy vấn không giới hạn, phân cấp bình luận gốc/con, cơ sở dữ liệu và xuất CSV):
```bash
python -m unittest discover tests
```
