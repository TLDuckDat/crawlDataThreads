import argparse
import sys
import subprocess
import os

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.crawler.threads_crawler import ThreadsCrawler
from src.crawler.browser import BrowserManager
from src.detector.toxic_engine import toxic_engine
from src.database.db_manager import db_manager
from src.exporter.exporter import exporter
from src.utils.logger import logger

def main():
    parser = argparse.ArgumentParser(
        description="Threads City Bad Data Collector & Toxic Analyzer - Công cụ cào và phân loại ngôn từ xúc phạm trên Threads"
    )
    subparsers = parser.add_subparsers(dest="command", help="Lệnh chức năng")

    # Command: crawl-post
    p_post = subparsers.add_parser("crawl-post", help="Cào bình luận chi tiết từ link bài viết Threads")
    p_post.add_argument("--url", "-u", required=True, help="URL bài viết trên Threads (vd: https://www.threads.net/@user/post/xxx)")
    p_post.add_argument("--max", "-m", type=int, default=50, help="Số lượng bình luận tối đa cần cào (nhập 0 hoặc dùng cờ --unlimited để không giới hạn, mặc định: 50)")
    p_post.add_argument("--unlimited", action="store_true", default=False, help="Cào không giới hạn (cào toàn bộ bình luận đến hết)")
    p_post.add_argument("--headless", action="store_true", default=True, help="Chạy ẩn trình duyệt (mặc định: True)")
    p_post.add_argument("--no-headless", action="store_false", dest="headless", help="Hiện cửa sổ trình duyệt Chrome")

    # Command: crawl-search
    p_search = subparsers.add_parser("crawl-search", help="Cào bài viết theo từ khóa tìm kiếm / drama trên Threads")
    p_search.add_argument("--query", "-q", required=True, help="Từ khóa tìm kiếm (vd: drama, bóc phốt, cãi nhau)")
    p_search.add_argument("--limit", "-l", type=int, default=30, help="Số lượng bài tối đa (nhập 0 hoặc dùng cờ --unlimited để không giới hạn, mặc định: 30)")
    p_search.add_argument("--unlimited", action="store_true", default=False, help="Cào không giới hạn (cào toàn bộ bài viết tìm được đến hết)")
    p_search.add_argument("--headless", action="store_true", default=True, help="Chạy ẩn trình duyệt")
    p_search.add_argument("--no-headless", action="store_false", dest="headless", help="Hiện cửa sổ trình duyệt")

    # Command: scan-text
    p_scan = subparsers.add_parser("scan-text", help="Kiểm tra độ độc hại, từ lóng, icon của một đoạn văn bản")
    p_scan.add_argument("--text", "-t", required=True, help="Nội dung văn bản cần kiểm tra")

    # Command: stats
    subparsers.add_parser("stats", help="Xem thống kê tổng quan dữ liệu độc hại đã thu thập trong CSDL")

    # Command: export-csv (Dedicated comments CSV)
    p_csv = subparsers.add_parser("export-csv", help="Xuất file CSV bình luận phân loại (Xấu luôn / Chưa rõ / Toàn bộ, chuẩn UTF-8 mở Excel không lỗi font)")
    p_csv.add_argument("--status", choices=["bad", "ambiguous", "clean", "all"], default="all", help="Lọc phân loại: 'bad' (Xấu luôn), 'ambiguous' (Chưa rõ/nghi ngờ), 'clean' (Trong sạch), 'all' (Tất cả để tự tổng hợp)")
    p_csv.add_argument("--type", choices=["all", "root", "reply"], default="all", help="Lọc loại bình luận: 'all' (Tất cả), 'root' (Chỉ bình luận gốc), 'reply' (Chỉ bình luận con / phản hồi)")
    p_csv.add_argument("--links", action="store_true", default=False, help="Kèm theo các cột link (Link bài gốc, comment, profile, parent_id) - Mặc định: tắt")

    # Command: export-curated (Fixed size Excel/CSV with 4 core columns + evaluation)
    p_curated = subparsers.add_parser("export-curated", help="Xuất file Excel/CSV chuẩn 4 cột (Nội dung, Điểm đánh giá, Bài viết, Chủ đề) đã fix size ô và wrap text")
    p_curated.add_argument("--format", "-f", choices=["xlsx", "csv"], default="xlsx", help="Định dạng xuất (xlsx đã căn chuẩn kích thước ô, csv)")
    p_curated.add_argument("--status", choices=["bad", "ambiguous", "clean", "all"], default="all", help="Lọc phân loại: 'bad', 'ambiguous', 'clean', 'all'")
    p_curated.add_argument("--type", choices=["all", "root", "reply"], default="all", help="Lọc loại: 'all', 'root', 'reply'")
    p_curated.add_argument("--limit", "-l", type=int, default=0, help="Số lượng dòng tối đa (0 là không giới hạn, mặc định: 0)")
    p_curated.add_argument("--columns", "-c", default=None, help="Tùy chọn chỉ xuất các cột cụ thể (ngăn cách bằng dấu phẩy, ví dụ: 'Nội dung,Điểm đánh giá,Bài viết')")

    # Command: import-evaluation (Active learning loop from Excel/CSV)
    p_import = subparsers.add_parser("import-evaluation", help="Nạp file Excel/CSV bạn đã tự đánh giá để cập nhật CSDL và tự động học từ mới nạp vào file JSON")
    p_import.add_argument("--file", "-i", required=True, help="Đường dẫn tới file Excel (.xlsx) hoặc CSV (.csv) đã được tự đánh giá")

    # Command: export
    p_export = subparsers.add_parser("export", help="Xuất dữ liệu ra file Excel, CSV, hoặc JSON")
    p_export.add_argument("--format", "-f", choices=["xlsx", "csv", "json"], default="xlsx", help="Định dạng xuất (xlsx, csv, json)")
    p_export.add_argument("--type", choices=["comments", "posts", "both"], default="both", help="Loại dữ liệu (comments, posts, both)")
    p_export.add_argument("--all", action="store_false", dest="toxic_only", default=True, help="Xuất toàn bộ thay vì chỉ dữ liệu độc hại")

    # Command: dashboard
    subparsers.add_parser("dashboard", help="Khởi chạy giao diện Web Dashboard (Streamlit UI)")

    # Command: login
    p_login = subparsers.add_parser("login", help="Mở trình duyệt đăng nhập Threads 1 lần để lưu phiên (Bỏ giới hạn 20 bình luận của Meta)")
    p_login.add_argument("--browser", choices=["chrome", "edge"], default=None, help="Chọn trình duyệt để đăng nhập (chrome hoặc edge, mặc định: tự động)")

    # Command: purge-foreign
    subparsers.add_parser(
        "purge-foreign",
        help="Dọn dẹp CSDL: Xóa các bình luận/bài đăng tiếng Trung, Nhật, Hàn, Thái, Ả Rập... khỏi SQLite, làm sạch ký tự ngoại ngữ trong dữ liệu hiện có"
    )

    # Command: clear-db
    p_clear = subparsers.add_parser(
        "clear-db",
        help="⚠️ XÓA TOÀN BỘ dữ liệu (comments, posts, sessions) trong CSDL SQLite. KHÔNG THỂ HOÀN TÁC!"
    )
    p_clear.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Bỏ qua bước xác nhận (dùng khi chạy script tự động)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "crawl-post":
        max_comments = 0 if args.unlimited else args.max
        limit_desc = "KHÔNG GIỚI HẠN (∞)" if (args.unlimited or args.max <= 0) else str(args.max)
        print(f"\n=======================================================")
        print(f"[*] ĐANG BẮT ĐẦU CÀO CHI TIẾT BÌNH LUẬN TỪ: {args.url}")
        print(f"[*] Số lượng: {limit_desc} | Headless: {args.headless}")
        print(f"=======================================================")
        crawler = ThreadsCrawler(headless=args.headless)
        res = crawler.crawl_post_and_comments(post_url=args.url, max_comments=max_comments)
        print(f"\n[+] KẾT QUẢ: Thu thập {res.get('comments_count', 0)} bình luận (Gốc: {res.get('root_comments_count', 0)}, Con: {res.get('child_comments_count', 0)}) | Phát hiện {res.get('toxic_comments_count', 0)} bình luận xúc phạm/từ lóng.")

    elif args.command == "crawl-search":
        limit_search = 0 if args.unlimited else args.limit
        limit_desc = "KHÔNG GIỚI HẠN (∞)" if (args.unlimited or args.limit <= 0) else str(args.limit)
        print(f"\n=======================================================")
        print(f"[*] TÌM KIẾM VÀ CÀO THREADS THEO TỪ KHÓA: '{args.query}'")
        print(f"[*] Số lượng: {limit_desc} | Headless: {args.headless}")
        print(f"=======================================================\n")
        crawler = ThreadsCrawler(headless=args.headless)
        res = crawler.crawl_search_query(query=args.query, limit=limit_search)
        print(f"\n[+] KẾT QUẢ: Thu thập {res.get('posts_count', 0)} bài đăng | Phát hiện {res.get('toxic_posts_count', 0)} bài đăng vi phạm.")

    elif args.command == "scan-text":
        res = toxic_engine.analyze(args.text)
        print("\n--- KẾT QUẢ PHÂN TÍCH VĂN BẢN & TỪ LÓNG ---")
        print(f"Văn bản: {args.text}")
        print(f"Trạng thái: {'⚠️ CÓ VI PHẠM / TỪ LÓNG ĐỘC HẠI' if res.is_toxic else '✅ TRONG SẠCH'}")
        print(f"Điểm Toxic Score: {res.score} / 1.0 (Mức độ: {res.severity_vi})")
        print(f"Từ lóng/xúc phạm: {', '.join(res.matched_words) if res.matched_words else 'Không có'}")
        print(f"Icon nhạy cảm: {', '.join(res.matched_emojis) if res.matched_emojis else 'Không có'}")
        print(f"Nhóm vi phạm: {', '.join(res.category_names) if res.category_names else 'Không có'}")

    elif args.command == "stats":
        stats = db_manager.get_stats()
        print("\n--- THỐNG KÊ CƠ SỞ DỮ LIỆU THREADS BAD DATA ---")
        print(f"Tổng bài đăng đã cào: {stats['total_posts']} (Độc hại: {stats['toxic_posts']})")
        print(f"Tổng bình luận đã cào: {stats['total_comments']} (Bình luận gốc: {stats['total_root_comments']}, Bình luận con/phản hồi: {stats['total_child_comments']} | Độc hại: {stats['toxic_comments']})")
        print(f"Tổng mẫu dữ liệu: {stats['total_items']}")
        print(f"Tỉ lệ nội dung xúc phạm: {stats['toxic_rate_percent']}%")
        print("\nTop từ ngữ / từ lóng xúc phạm xuất hiện nhiều nhất:")
        for idx, item in enumerate(db_manager.get_top_toxic_words(10), 1):
            print(f"  {idx}. '{item['word']}': {item['count']} lần")

    elif args.command == "export-csv":
        status_labels = {
            "bad": "Chỉ bình luận ĐÁNH GIÁ LÀ XẤU LUÔN (Rõ ràng)",
            "ambiguous": "Chỉ bình luận CHƯA RÕ (Nghi ngờ / Cần duyệt lại)",
            "clean": "Chỉ bình luận Trong sạch",
            "all": "Toàn bộ bình luận (Đã phân loại Xấu / Chưa rõ / Sạch để tự tổng hợp)"
        }
        type_labels = {
            "all": "Cả gốc & con",
            "root": "Chỉ bình luận gốc",
            "reply": "Chỉ bình luận con (phản hồi)"
        }
        scope_str = status_labels.get(args.status, args.status)
        type_str = f" [{type_labels.get(args.type, args.type)}]"
        link_str = " (Kèm link)" if args.links else " (Chỉ nội dung bình luận, không kèm link)"
        print(f"[*] Đang xuất CSV bình luận: {scope_str}{type_str}{link_str}...")
        path = exporter.export_comments_csv(filter_status=args.status, filter_comment_type=args.type, include_links=args.links)
        print(f"[+] Xuất thành công file CSV tại:\n👉 {path}")
        print(f"[*] Định dạng UTF-8-BOM: Bạn có thể mở trực tiếp bằng Microsoft Excel để lọc/tổng hợp mà không bị lỗi font tiếng Việt.")

    elif args.command == "export-curated":
        limit_val = None if args.limit <= 0 else args.limit
        cols_val = [c.strip() for c in args.columns.split(",") if c.strip()] if args.columns else None
        print(f"[*] Đang xuất file 4 cột chuẩn (Nội dung, Điểm đánh giá, Bài viết, Chủ đề bài viết)...")
        if cols_val:
            print(f"[*] Tùy chọn chỉ xuất {len(cols_val)} cột: {', '.join(cols_val)}")
        if args.format == "xlsx":
            path = exporter.export_curated_excel(
                filter_status=args.status,
                filter_comment_type=args.type,
                limit=limit_val,
                columns=cols_val
            )
            print(f"[+] Đã xuất file Excel chuẩn đã fix kích thước ô & wrap text tại:\n👉 {path}")
            print(f"[*] File có sẵn cột 'Tự đánh giá của bạn' và 'Từ lóng mới bổ sung' để bạn tự phân loại và nạp lại vào hệ thống.")
        else:
            path = exporter.export_curated_csv(
                filter_status=args.status,
                filter_comment_type=args.type,
                limit=limit_val,
                columns=cols_val
            )
            print(f"[+] Đã xuất file CSV chuẩn UTF-8-BOM tại:\n👉 {path}")

    elif args.command == "import-evaluation":
        file_path = args.file
        if not os.path.exists(file_path):
            print(f"[!] Lỗi: Không tìm thấy file tại '{file_path}'")
            sys.exit(1)

        import pandas as pd
        print(f"[*] Đang đọc dữ liệu đánh giá từ file: {file_path}...")
        try:
            if file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                df_eval = pd.read_excel(file_path)
            else:
                df_eval = pd.read_csv(file_path)
        except Exception as e:
            print(f"[!] Lỗi khi đọc file: {e}")
            sys.exit(1)

        # Locate relevant columns
        col_id = None
        for c in ["Mã ID", "id", "comment_id", "ID"]:
            if c in df_eval.columns:
                col_id = c
                break

        col_review = None
        for c in ["Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)", "Tự đánh giá của bạn", "user_review", "Đánh giá"]:
            if c in df_eval.columns:
                col_review = c
                break

        col_content = None
        for c in ["Nội dung", "content", "Nội dung bình luận"]:
            if c in df_eval.columns:
                col_content = c
                break

        col_post = "Bài viết" if "Bài viết" in df_eval.columns else None
        col_topic = "Chủ đề bài viết" if "Chủ đề bài viết" in df_eval.columns else None
        col_new_words = None
        for c in ["Từ lóng mới bổ sung (nếu có)", "Từ lóng mới", "new_keywords"]:
            if c in df_eval.columns:
                col_new_words = c
                break

        if not col_id or not col_review:
            print(f"[!] Lỗi: File thiếu cột ID hoặc cột Tự đánh giá.")
            print(f"Các cột tìm thấy: {list(df_eval.columns)}")
            sys.exit(1)

        updated_count = 0
        new_keywords_total = []
        for _, row in df_eval.iterrows():
            rev_val = str(row.get(col_review, "")).strip()
            if not rev_val or rev_val.lower() == "nan":
                continue

            # Standardize review value
            rev_clean = rev_val.lower()
            if "xấu" in rev_clean or "bad" in rev_clean or "độc" in rev_clean:
                user_review_tag = "bad"
            elif "sạch" in rev_clean or "clean" in rev_clean:
                user_review_tag = "clean"
            elif "chưa rõ" in rev_clean or "ambiguous" in rev_clean or "nghi" in rev_clean:
                user_review_tag = "ambiguous"
            else:
                user_review_tag = rev_val

            comment_id = str(row.get(col_id, "")).strip()
            comment_text = str(row.get(col_content, "")).strip() if col_content else ""
            post_context = str(row.get(col_post, "")).strip() if col_post else ""
            topic = str(row.get(col_topic, "")).strip() if col_topic else ""
            new_kw_str = str(row.get(col_new_words, "")).strip() if col_new_words else ""
            new_keywords = [w.strip() for w in new_kw_str.split(",") if w.strip() and w.strip().lower() != "nan"]

            # 1. Update SQLite database
            db_manager.update_user_review(
                comment_id=comment_id,
                user_review=user_review_tag,
                user_keywords=new_keywords
            )

            # 2. Feed into Active Learning loop (toxic_keywords.json + training_dataset.json)
            learn_res = toxic_engine.learn_from_user_evaluation(
                text=comment_text,
                user_review=user_review_tag,
                new_keywords=new_keywords,
                post_context=post_context,
                topic=topic
            )
            if learn_res.get("added_keywords"):
                new_keywords_total.extend(learn_res["added_keywords"])
            updated_count += 1

        print(f"\n=======================================================")
        print(f"[+] NẠP VÀ HỌC DỮ LIỆU ĐÁNH GIÁ THÀNH CÔNG!")
        print(f"=======================================================")
        print(f"[*] Tổng số bình luận đã cập nhật tự đánh giá: {updated_count}")
        if new_keywords_total:
            print(f"[*] Đã tự động nạp thêm {len(new_keywords_total)} từ lóng mới vào từ điển config/toxic_keywords.json: {list(set(new_keywords_total))}")
        print(f"[*] Đã ghi nhận các mẫu dữ liệu vào dataset học máy: data/training_dataset.json")
        print(f"[*] Từ điển và bộ phân loại toxic_engine đã tự động nạp lại để áp dụng ngay lập tức!")

    elif args.command == "export":
        print(f"[*] Đang xuất dữ liệu định dạng: {args.format.upper()}...")
        if args.format == "xlsx":
            path = exporter.export_to_excel(table_type=args.type, toxic_only=args.toxic_only)
        elif args.format == "csv":
            path = exporter.export_to_csv(table_type=args.type, toxic_only=args.toxic_only)
        else:
            path = exporter.export_to_json(table_type=args.type, toxic_only=args.toxic_only)
        print(f"[+] Xuất thành công tại:\n👉 {path}")

    elif args.command == "purge-foreign":
        print("\n=======================================================")
        print("[*] DỌN DẸP DỮ LIỆU TIẾNG TRUNG, NHẬT, HÀN... TRONG CSDL")
        print("=======================================================")
        print("[*] Đang quét và xóa các bình luận / bài đăng bằng tiếng nước ngoài...")
        result = db_manager.purge_foreign_language_records()
        print(f"\n[+] HOÀN TẤT DỌN DẸP!")
        print(f"    - Đã XÓA {result['purged_comments']} bình luận hoàn toàn là tiếng Trung / Nhật / Hàn / Thái...")
        print(f"    - Đã XÓA {result['purged_posts']} bài đăng hoàn toàn là tiếng nước ngoài")
        print(f"    - Đã LÀM SẠCH {result['cleaned_comments']} bình luận có ký tự ngoại ngữ lẫn lộn (giữ lại phần Việt/Anh)")
        print("\n[*] CSDL đã sạch! Từ đây trở đi crawler sẽ tự động bỏ qua nội dung tiếng nước ngoài khi cào.")

    elif args.command == "clear-db":
        stats = db_manager.get_stats()
        print("\n=======================================================")
        print("⚠️  XÓA TOÀN BỘ DỮ LIỆU TRONG CƠ SỞ DỮ LIỆU")
        print("=======================================================")
        print(f"[*] Hiện tại CSDL đang chứa:")
        print(f"    - {stats['total_comments']} bình luận (Gốc: {stats.get('total_root_comments', 0)}, Con: {stats.get('total_child_comments', 0)})")
        print(f"    - {stats['total_posts']} bài đăng")
        print(f"    - Tỉ lệ độc hại: {stats['toxic_rate_percent']}%")
        print(f"\n⚠️  CẢNH BÁO: Hành động này sẽ XÓA VĨNH VIỄN toàn bộ dữ liệu trên. KHÔNG THỂ HOÀN TÁC!")

        confirmed = args.yes
        if not confirmed:
            try:
                answer = input("\n❓ Bạn có chắc chắn muốn xóa hết không? Gõ 'XOA' để xác nhận, hoặc nhấn Enter để hủy: ").strip()
                confirmed = (answer == "XOA")
            except (EOFError, KeyboardInterrupt):
                confirmed = False

        if not confirmed:
            print("\n[~] Đã HỦY thao tác xóa. Dữ liệu vẫn được giữ nguyên.")
            sys.exit(0)

        result = db_manager.clear_all_data()
        print(f"\n[+] ĐÃ XÓA TOÀN BỘ DỮ LIỆU THÀNH CÔNG!")
        print(f"    - Đã xóa {result['deleted_comments']} bình luận")
        print(f"    - Đã xóa {result['deleted_posts']} bài đăng")
        print(f"    - Đã xóa {result['deleted_sessions']} phiên cào")
        print(f"\n[*] CSDL hiện đang trống. Bạn có thể bắt đầu thu thập dữ liệu mới!")

    elif args.command == "dashboard":

        print("[*] Đang khởi động Streamlit Web Dashboard...")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app_dashboard.py"])

    elif args.command == "login":
        target_b = args.browser or BrowserManager.get_active_browser()
        print("\n=======================================================")
        print("[*] ĐĂNG NHẬP THREADS ĐỂ LƯU PHIÊN (VƯỢT GIỚI HẠN 20 BÌNH LUẬN)")
        print("=======================================================")
        print(f"[*] Đang khởi chạy trình duyệt: {target_b.upper()}...")
        print("[*] Vui lòng đăng nhập tài khoản Threads / Instagram của bạn trên cửa sổ vừa mở.")
        print("[*] Cookie & Session sẽ được lưu vĩnh viễn trong thư mục hồ sơ của dự án.")
        print("[*] Sau khi đăng nhập thành công trên Threads, hãy quay lại đây và nhấn Enter.")
        driver = BrowserManager.get_driver(headless=False, use_profile=True, preferred_browser=args.browser)
        try:
            driver.get("https://www.threads.net/login")
            input("\n👉 Nhấn ENTER tại đây sau khi bạn đã đăng nhập xong trên trình duyệt: ")
            print(f"[+] Đã lưu phiên đăng nhập thành công cho trình duyệt {BrowserManager.get_active_browser().upper()}! Các lần cào tới sẽ có thể cào toàn bộ 1.3K+ bình luận mà không bị Meta chặn.")
        finally:
            try:
                driver.quit()
            except Exception:
                pass

if __name__ == "__main__":
    main()
