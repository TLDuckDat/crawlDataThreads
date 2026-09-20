import sys
from streamlit.runtime import exists

# Auto-launch with `streamlit run` if executed directly via `python app_dashboard.py`
if not exists():
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", __file__]
    sys.exit(stcli.main())

import streamlit as st
import pandas as pd
import json
import re
import html
import altair as alt
from datetime import datetime

from config.settings import DEFAULT_MAX_COMMENTS, DEFAULT_SCROLL_DELAY, CHROME_PROFILE_DIR
from src.database.db_manager import db_manager
from src.detector.toxic_engine import toxic_engine
from src.crawler.threads_crawler import ThreadsCrawler
from src.crawler.browser import BrowserManager
from src.crawler.task_manager import crawler_task_manager
from src.exporter.exporter import exporter

# Page configuration
st.set_page_config(
    page_title="Threads City Bad Data Collector & Toxic Analyzer",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    .toxic-badge {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .clean-badge {
        background-color: #DCFCE7;
        color: #166534;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .emoji-tag {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .focus-card {
        background-color: #FFFFFF;
        border: 2px solid #E2E8F0;
        border-radius: 14px;
        padding: 22px 26px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
        margin-bottom: 18px;
    }
    .focus-card-toxic {
        border-left: 7px solid #EF4444;
    }
    .focus-card-clean {
        border-left: 7px solid #10B981;
    }
    .focus-card-ambiguous {
        border-left: 7px solid #F59E0B;
    }
    .comment-large-text {
        font-size: 1.28rem;
        line-height: 1.75;
        color: #0F172A;
        background-color: #F8FAFC;
        padding: 18px 22px;
        border-radius: 10px;
        border: 1px solid #E2E8F0;
        margin: 14px 0;
        white-space: pre-wrap !important;
        overflow-wrap: break-word !important;
        word-wrap: break-word !important;
        word-break: break-word !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .context-quote {
        font-size: 0.95rem;
        color: #475569;
        background-color: #F1F5F9;
        padding: 12px 18px;
        border-radius: 8px;
        border-left: 4px solid #94A3B8;
        margin-top: 10px;
        line-height: 1.55;
        white-space: pre-wrap !important;
        overflow-wrap: break-word !important;
        word-wrap: break-word !important;
        word-break: break-word !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions for Single-Comment Review
from src.detector.text_normalizer import highlight_comment_text, extract_candidate_words

# Sidebar
st.sidebar.title("🛡️ Threads Toxic Guard")
st.sidebar.caption("Thu thập & phát hiện từ lóng, xúc phạm, icon độc hại trên Threads City")

menu_options = [
    "🚀 Trung tâm Cào dữ liệu",
    "⚡ Gán nhãn từng bình luận (Siêu tốc)",
    "📥 Xuất dữ liệu Excel & CSV (Fix size / Tự tổng hợp)",
    "📋 Dữ liệu & Tự đánh giá (Học máy)",
    "📊 Thống kê & Phân tích",
    "🔍 Kiểm tra văn bản & Icon",
    "📚 Từ điển Từ lóng & Icon"
]

if "main_menu_choice" not in st.session_state:
    st.session_state["main_menu_choice"] = menu_options[0]
if st.session_state["main_menu_choice"] not in menu_options:
    st.session_state["main_menu_choice"] = menu_options[0]

def on_menu_change():
    st.session_state["main_menu_choice"] = st.session_state["sidebar_radio_menu"]

menu = st.sidebar.radio(
    "Chức năng chính",
    menu_options,
    index=menu_options.index(st.session_state["main_menu_choice"]),
    key="sidebar_radio_menu",
    on_change=on_menu_change
)

# Persistent Background Task Status in Sidebar
@st.fragment(run_every=2)
def render_sidebar_task_status():
    task = crawler_task_manager.get_status()
    if task["is_running"]:
        target_display = task['target'][:26] + ("..." if len(task['target']) > 26 else "")
        st.markdown(f"""
        <div style='background: #EFF6FF; border: 1.5px solid #3B82F6; padding: 10px; border-radius: 8px; margin-top: 15px;'>
            <div style='color: #1D4ED8; font-weight: bold; font-size: 13px;'>🟢 ĐANG CÀO DỮ LIỆU NGẦM</div>
            <div style='font-size: 11px; color: #475569; margin: 4px 0; word-break: break-all;'>🎯 <b>Mục tiêu:</b> {target_display}</div>
            <div style='font-size: 12px; color: #0F172A;'>📊 <b>Đã cào:</b> {task['scraped_count']} ({task['toxic_count']} độc hại)</div>
            <div style='font-size: 11px; color: #64748B;'>⏱️ <b>Thời gian:</b> {int(task['elapsed_seconds'])}s</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("⏹️ Dừng cào dữ liệu", key="sidebar_stop_crawl_btn", use_container_width=True):
            crawler_task_manager.stop_crawl()
            st.rerun()
    elif task["result"] and not task["error"]:
        st.markdown(f"""
        <div style='background: #ECFDF5; border: 1px solid #A7F3D0; padding: 8px; border-radius: 8px; margin-top: 15px;'>
            <div style='color: #047857; font-weight: bold; font-size: 12px;'>✅ LƯỢT CÀO GẦN NHẤT XONG</div>
            <div style='font-size: 11px; color: #065F46;'>Đã cào: {task['scraped_count']} ({task['toxic_count']} vi phạm)</div>
        </div>
        """, unsafe_allow_html=True)

with st.sidebar:
    render_sidebar_task_status()

# TAB 1: CRAWL CENTER
if menu == "🚀 Trung tâm Cào dữ liệu":
    st.markdown('<div class="main-header">🚀 Trung tâm Thu thập Dữ liệu Threads</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Cào dữ liệu chạy ngầm liên tục: Bạn có thể tự do chuyển sang các tab khác mà tiến trình cào vẫn tiếp tục hoạt động!</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style='background:#EFF6FF; border:1.5px solid #3B82F6; border-radius:8px; padding:8px 14px; margin-bottom:12px; display:inline-block; font-size:13px;'>
        🌏 <b>Tự động lọc ngôn ngữ:</b>
        Hệ thống <b>bỏ qua hoàn toàn</b> các bình luận và bài viết bằng
        <b>tiếng Trung 🇨🇳 · Nhật 🇯🇵 · Hàn 🇰🇷 · Thái · Ả Rập · Nga</b>
        — chỉ giữ lại nội dung <b>Tiếng Việt 🇻🇳 và Tiếng Anh 🇬🇧</b>.
    </div>
    """, unsafe_allow_html=True)

    @st.fragment(run_every=2)
    def render_crawl_live_panel():
        task = crawler_task_manager.get_status()
        if task["is_running"]:
            st.info(f"🔄 **TIẾN TRÌNH CÀO ĐANG CHẠY TRONG NỀN** — Bạn có thể chuyển sang tab khác tùy ý mà không sợ bị dừng!")
            
            c_m1, c_m2, c_m3, c_m4 = st.columns(4)
            c_m1.metric("Tổng đã cào", task["scraped_count"])
            c_m2.metric("Bình luận gốc", task["root_count"])
            c_m3.metric("Bình luận con (Reply)", task["child_count"])
            c_m4.metric("Nội dung vi phạm", task["toxic_count"])

            # Progress bar
            if task["max_items"] > 0:
                pct = min(1.0, task["scraped_count"] / task["max_items"])
                st.progress(pct, text=f"Tiến độ: {task['scraped_count']} / {task['max_items']} ({int(pct*100)}%) | Thời gian: {int(task['elapsed_seconds'])}s")
            else:
                st.progress(min(1.0, (task["scraped_count"] % 100) / 100.0), text=f"Chế độ không giới hạn: Đã cào {task['scraped_count']} mục | Thời gian: {int(task['elapsed_seconds'])}s...")

            st.caption(f"Trạng thái: {task['status_message']}")

            if task["latest_item"]:
                it = task["latest_item"]
                is_t = it.get("is_toxic", False)
                badge = f"<span class='toxic-badge'>⚠️ VI PHẠM ({it.get('score')} - {it.get('severity_vi')})</span>" if is_t else "<span class='clean-badge'>✅ Trong sạch</span>"
                c_badge = f"<span style='background:#E0E7FF; color:#3730A3; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; margin-left:6px;'>↳ Phản hồi {it.get('reply_to', '')}</span>" if it.get('is_reply') else "<span style='background:#F1F5F9; color:#475569; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; margin-left:6px;'>💬 Bình luận gốc</span>"
                words = f"<br><b>Từ lóng/xúc phạm:</b> {', '.join(it.get('words', []))}" if it.get('words') else ""
                emojis = f"<br><b>Icon nhạy cảm:</b> {', '.join(it.get('emojis', []))}" if it.get('emojis') else ""
                st.markdown(f"""
                <div style='background: #F8FAFC; padding: 12px; border-radius: 8px; border-left: 4px solid {'#EF4444' if is_t else '#10B981'}; margin-top: 10px;'>
                    <b>Mục mới nhất:</b> @{it.get('username')} | {badge} {c_badge}
                    <br><b>Nội dung:</b> {it.get('content')[:140]}...
                    {words}
                    {emojis}
                </div>
                """, unsafe_allow_html=True)

            st.write("")
            if st.button("⏹️ DỪNG QUÁ TRÌNH CÀO", type="secondary", use_container_width=True):
                crawler_task_manager.stop_crawl()
                st.rerun()

    task_status = crawler_task_manager.get_status()
    if task_status["is_running"]:
        render_crawl_live_panel()
    else:
        # Show recent result summary if available
        if task_status["result"]:
            res = task_status["result"]
            st.success(f"🎉 Lượt cào gần nhất đã hoàn tất! Thu thập: {task_status['scraped_count']} mục (Gốc: {task_status['root_count']}, Con/phản hồi: {task_status['child_count']}). Phát hiện: {task_status['toxic_count']} độc hại.")
            if task_status["login_wall_hit"]:
                st.warning("⚠️ **Lưu ý:** Quá trình cào đã dừng lại do chạm tường đăng nhập của Meta Threads (~20 bình luận gốc). Nếu bạn muốn cào toàn bộ hơn 1.300 bình luận, vui lòng mở mục **🔑 Đăng nhập Threads** ở bên dưới để đăng nhập tài khoản 1 lần duy nhất.")
            if st.button("✖️ Đóng thông báo hoàn tất"):
                crawler_task_manager.reset_status()
                st.rerun()

        crawl_type = st.radio("Chế độ cào dữ liệu:", ["Link bài viết cụ thể (Cào sâu bình luận)", "Từ khóa tìm kiếm / Drama nóng"], horizontal=True)

        col1, col2 = st.columns([3, 1])
        with col1:
            if crawl_type == "Link bài viết cụ thể (Cào sâu bình luận)":
                target_input = st.text_input(
                    "Nhập URL bài viết Threads:",
                    placeholder="https://www.threads.net/@zuck/post/DdZ7sQvkTFn hoặc bất kỳ link bài viết nào"
                )
            else:
                target_input = st.text_input(
                    "Nhập từ khóa tìm kiếm (Drama / Phốt / Từ lóng / Chủ đề nóng):",
                    placeholder="bóc phốt, cãi nhau, drama, tranh cãi, bốc phốt..."
                )

        with col2:
            unlimited_crawl = st.checkbox(
                "♾️ KHÔNG GIỚI HẠN (Cào đến hết)",
                value=False,
                help="Tự động cuộn và cào liên tục cho tới khi không còn bình luận/bài viết nào mới."
            )
            if unlimited_crawl:
                max_items = 0
                st.info("⚡ Chế độ không giới hạn: Không giới hạn số lượng, cào liên tục đến khi hết nội dung.")
            else:
                max_items = st.number_input("Số lượng tối đa:", min_value=1, max_value=1000000, value=50, step=10)

        with st.expander("🔑 Đăng nhập Threads (Để cào toàn bộ 1.3K+ bình luận không bị giới hạn 20)", expanded=False):
            st.markdown("""
            **Lưu ý quan trọng từ Meta Threads:**
            - Mặc định Threads giới hạn khách chưa đăng nhập chỉ xem được tối đa **~20 bình luận**.
            - Để cào toàn bộ **hơn 1.300 bình luận** của bài viết, bạn chỉ cần đăng nhập tài khoản Threads/Instagram 1 lần duy nhất.
            - Trình duyệt sẽ lưu phiên đăng nhập vĩnh viễn trong thư mục hồ sơ của dự án.
            """)
            curr_b = BrowserManager.get_active_browser().upper()
            st.caption(f"Trình duyệt mặc định hiện tại: **{curr_b}**")
            c_login1, c_login2 = st.columns(2)
            with c_login1:
                if st.button("🌐 Đăng nhập bằng Google Chrome", use_container_width=True):
                    st.info("Đang mở Google Chrome... Hãy đăng nhập trên cửa sổ vừa xuất hiện!")
                    BrowserManager.launch_login_window(preferred_browser="chrome")
            with c_login2:
                if st.button("🌐 Đăng nhập bằng Microsoft Edge", use_container_width=True):
                    st.info("Đang mở Microsoft Edge... Hãy đăng nhập trên cửa sổ vừa xuất hiện!")
                    BrowserManager.launch_login_window(preferred_browser="edge")

        with st.expander("⚙️ Tùy chọn nâng cao (Trình duyệt & Tốc độ cuộn)", expanded=False):
            c_adv1, c_adv2 = st.columns(2)
            with c_adv1:
                headless = st.checkbox("Chạy ẩn trình duyệt (Headless mode)", value=True)
            with c_adv2:
                delay = st.slider("Độ trễ giữa các lần cuộn (giây) - Đảm bảo tải đủ icon và nội dung:", min_value=1.5, max_value=6.0, value=2.0, step=0.5)

        if st.button("▶️ BẮT ĐẦU CÀO DỮ LIỆU", type="primary", use_container_width=True):
            if not target_input.strip():
                st.warning("Vui lòng nhập URL bài viết hoặc từ khóa tìm kiếm!")
            else:
                if "Link bài viết cụ thể" in crawl_type:
                    started = crawler_task_manager.start_post_crawl(
                        post_url=target_input.strip(),
                        max_comments=max_items,
                        scroll_delay=delay,
                        headless=headless
                    )
                else:
                    started = crawler_task_manager.start_search_crawl(
                        query=target_input.strip(),
                        limit=max_items,
                        scroll_delay=delay,
                        headless=headless
                    )
                if started:
                    st.success("🚀 Đã khởi động tiến trình cào dữ liệu chạy ngầm! Bạn có thể tự do chuyển sang tab khác.")
                    st.rerun()
                else:
                    st.error("Tiến trình cào khác đang chạy. Vui lòng dừng tiến trình cũ trước khi bắt đầu lượt mới!")

# TAB: FOCUS SINGLE-COMMENT REVIEW & FAST LABELING
elif menu == "⚡ Gán nhãn từng bình luận (Siêu tốc)":
    st.markdown('<div class="main-header">⚡ Gán Nhãn &amp; Chọn Từ Xấu Từng Bình Luận (Siêu Tốc)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Hiển thị trọn vẹn 100% từng bình luận với chữ to rõ — Không cần double click — Chọn trực tiếp từ xấu trong câu &amp; Gán nhãn 1-click tự động chuyển tiếp!</div>', unsafe_allow_html=True)

    # 1. Progress Banner & Metrics
    prog = db_manager.get_review_progress()
    total_db_comments = prog["total"]
    reviewed_db_comments = prog["reviewed"]
    unreviewed_db_comments = prog["unreviewed"]
    pct_reviewed = prog["percent"]

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Tổng bình luận CSDL", f"{total_db_comments:,}")
    col_m2.metric("Đã tự gán nhãn", f"{reviewed_db_comments:,} ({pct_reviewed}%)")
    col_m3.metric("Chưa gán nhãn (Cần duyệt)", f"{unreviewed_db_comments:,}")
    col_m4.metric("Đã gán vi phạm", f"{prog['user_bad']} vi phạm / {prog['user_clean']} sạch")

    st.progress(
        min(1.0, max(0.0, pct_reviewed / 100.0)),
        text=f"Tiến độ hoàn thành: {reviewed_db_comments} / {total_db_comments} bình luận ({pct_reviewed}%)"
    )

    st.divider()

    # 2. Queue Filters & Settings Toolbar
    with st.expander("⚙️ Bộ lọc hàng đợi & Tùy chọn hiển thị", expanded=True):
        c_f1, c_f2, c_f3, c_f4 = st.columns([2.2, 1.8, 1.8, 2.2])

        with c_f1:
            review_filter_label = st.selectbox(
                "Trạng thái gán nhãn:",
                [
                    "⚡ Chưa gán nhãn (Khuyên dùng)",
                    "📋 Toàn bộ bình luận",
                    "🟡 Chỉ câu nghi ngờ / Chưa rõ (Ambiguous)",
                    "🔴 Chỉ câu vi phạm (Bad)",
                    "🟢 Chỉ câu trong sạch (Clean)",
                    "✅ Đã tự gán nhãn (Xem lại)"
                ],
                index=0,
                key="focus_filter_review_select"
            )

        with c_f2:
            type_filter_label = st.selectbox(
                "Loại bình luận:",
                ["Tất cả (Gốc & Con)", "Chỉ bình luận gốc", "Chỉ phản hồi (Reply)"],
                index=0,
                key="focus_filter_type_select"
            )

        with c_f3:
            order_label = st.selectbox(
                "Thứ tự hiển thị:",
                ["Mới nhất trước", "Cũ nhất trước", "Điểm Toxic cao -> thấp", "Chưa duyệt lên đầu"],
                index=0,
                key="focus_order_select"
            )

        with c_f4:
            search_query = st.text_input(
                "Tìm kiếm nội dung / tác giả / từ khóa:",
                "",
                key="focus_search_input",
                placeholder="Nhập từ khóa cần tìm..."
            )

    # Map labels to query codes
    rev_map = {
        "⚡ Chưa gán nhãn (Khuyên dùng)": "unreviewed",
        "📋 Toàn bộ bình luận": "all",
        "🟡 Chỉ câu nghi ngờ / Chưa rõ (Ambiguous)": "ambiguous",
        "🔴 Chỉ câu vi phạm (Bad)": "bad",
        "🟢 Chỉ câu trong sạch (Clean)": "clean",
        "✅ Đã tự gán nhãn (Xem lại)": "reviewed"
    }
    t_map = {
        "Tất cả (Gốc & Con)": "all",
        "Chỉ bình luận gốc": "root",
        "Chỉ phản hồi (Reply)": "reply"
    }
    ord_map = {
        "Mới nhất trước": "newest",
        "Cũ nhất trước": "oldest",
        "Điểm Toxic cao -> thấp": "toxic_score_desc",
        "Chưa duyệt lên đầu": "unreviewed_first"
    }

    current_filter_rev = rev_map[review_filter_label]
    current_filter_t = t_map[type_filter_label]
    current_ord = ord_map[order_label]

    # Reset focus_idx if filter state changes
    filter_sig = f"{current_filter_rev}_{current_filter_t}_{current_ord}_{search_query}"
    if st.session_state.get("last_filter_sig") != filter_sig:
        st.session_state["last_filter_sig"] = filter_sig
        st.session_state["focus_current_idx"] = 0

    # Total matching comments in queue
    total_matching = db_manager.count_focus_review_comments(
        filter_review=current_filter_rev,
        filter_type=current_filter_t,
        search_kw=search_query
    )

    if total_matching == 0:
        if current_filter_rev == "unreviewed":
            st.balloons()
            st.success("🎉 **XUẤT SẮC!** Toàn bộ bình luận trong nhóm này đã được bạn gán nhãn hoàn tất!")
        else:
            st.info("ℹ️ Không tìm thấy bình luận nào phù hợp với bộ lọc hiện tại.")
    else:
        # Clamp index
        if "focus_current_idx" not in st.session_state:
            st.session_state["focus_current_idx"] = 0
        st.session_state["focus_current_idx"] = max(0, min(st.session_state["focus_current_idx"], total_matching - 1))
        cur_idx = st.session_state["focus_current_idx"]

        # 3. Top Navigation & Auto-advance Bar
        c_nav1, c_nav2, c_nav3, c_nav4, c_nav5, c_nav6 = st.columns([1, 1.2, 2.5, 1.2, 1, 2.4])

        with c_nav1:
            if st.button("⏮️ Đầu", use_container_width=True, disabled=(cur_idx == 0)):
                st.session_state["focus_current_idx"] = 0
                st.rerun()

        with c_nav2:
            if st.button("⬅️ Trước", use_container_width=True, disabled=(cur_idx == 0)):
                st.session_state["focus_current_idx"] = max(0, cur_idx - 1)
                st.rerun()

        with c_nav3:
            jump_idx = st.number_input(
                f"Đang xem câu: (1 - {total_matching:,})",
                min_value=1,
                max_value=total_matching,
                value=cur_idx + 1,
                step=1,
                label_visibility="collapsed",
                key=f"jump_input_{cur_idx}_{total_matching}"
            )
            if jump_idx - 1 != cur_idx:
                st.session_state["focus_current_idx"] = jump_idx - 1
                st.rerun()

        with c_nav4:
            if st.button("➡️ Sau", use_container_width=True, disabled=(cur_idx >= total_matching - 1)):
                st.session_state["focus_current_idx"] = min(total_matching - 1, cur_idx + 1)
                st.rerun()

        with c_nav5:
            if st.button("⏭️ Cuối", use_container_width=True, disabled=(cur_idx >= total_matching - 1)):
                st.session_state["focus_current_idx"] = total_matching - 1
                st.rerun()

        with c_nav6:
            auto_advance = st.checkbox(
                "⚡ Tự động chuyển tiếp khi bấm nhãn",
                value=True,
                key="auto_advance_cb",
                help="Khi bấm 1 trong 3 nút gán nhãn, hệ thống sẽ tự động lưu và chuyển sang bình luận tiếp theo ngay lập tức."
            )

        # 4. Fetch and Render Current Comment Item
        item = db_manager.get_focus_review_comment_at_index(
            index=cur_idx,
            filter_review=current_filter_rev,
            filter_type=current_filter_t,
            search_kw=search_query,
            order_by=current_ord
        )

        if item:
            content_text = item.get("content", "")

            # Dynamic Live Analysis: Always run latest toxic engine on unreviewed comment
            # so any newly learned keyword/slang from previous reviews is IMMEDIATELY recognized!
            live_analysis = toxic_engine.analyze(content_text)
            
            # Combine static database matches with live matches from newly learned dictionary
            combined_matched_words = list(set(item.get("matched_words_list", []) + live_analysis.matched_words))
            combined_matched_emojis = list(set(item.get("matched_emojis_list", []) + live_analysis.matched_emojis))

            # Determine card border and system score styling
            if item.get("is_user_reviewed"):
                sys_score = round(item.get("toxic_score", 0.0), 2)
                sys_severity = item.get("severity_vi", "Trong sạch")
                is_sys_toxic = item.get("is_toxic", False) or item.get("review_status") == "bad" or sys_score >= 0.5
                is_sys_ambiguous = item.get("review_status") == "ambiguous" or (0.15 <= sys_score < 0.5)
            else:
                sys_score = round(max(item.get("toxic_score", 0.0), live_analysis.score), 2)
                sys_severity = live_analysis.severity_vi if live_analysis.is_toxic else item.get("severity_vi", "Trong sạch")
                is_sys_toxic = live_analysis.is_toxic or item.get("is_toxic", False) or sys_score >= 0.5
                is_sys_ambiguous = not is_sys_toxic and (live_analysis.review_status == "ambiguous" or (0.15 <= sys_score < 0.5))

            card_border_class = "focus-card-toxic" if is_sys_toxic else ("focus-card-ambiguous" if is_sys_ambiguous else "focus-card-clean")

            # Meta badges
            author_user = item.get("author_username") or "threads_user"
            author_name = item.get("author_name") or author_user
            author_url = item.get("author_profile_url") or f"https://www.threads.net/@{author_user}"
            comment_url = item.get("comment_url") or item.get("post_url") or ""
            is_reply = item.get("is_reply", 0)
            reply_to = item.get("reply_to") or ""
            c_type_label = f"↳ Phản hồi @{reply_to}" if (is_reply and reply_to) else ("↳ Bình luận con" if is_reply else "💬 Bình luận gốc")
            likes_count = item.get("likes", 0)
            posted_time = item.get("posted_at") or ""

            # System prediction badge HTML
            detected_label = f" [Phát hiện: {', '.join(combined_matched_words[:3])}]" if combined_matched_words else ""
            if is_sys_toxic:
                sys_badge_html = f"<span class='toxic-badge'>⚠️ Hệ thống chấm: VI PHẠM ({sys_score} - {sys_severity}){detected_label}</span>"
            elif is_sys_ambiguous:
                sys_badge_html = f"<span style='background:#FEF3C7; color:#92400E; padding:4px 10px; border-radius:6px; font-weight:600; font-size:0.85rem;'>🟡 Hệ thống chấm: NGHI NGỜ ({sys_score}){detected_label}</span>"
            else:
                sys_badge_html = f"<span class='clean-badge'>✅ Hệ thống chấm: Trong sạch ({sys_score})</span>"

            # User review status if already reviewed
            user_badge_html = ""
            if item.get("is_user_reviewed"):
                u_rev = item.get("user_review", "")
                if u_rev == "bad":
                    user_badge_html = "<span style='background:#FEE2E2; color:#B91C1C; padding:4px 10px; border-radius:6px; font-weight:700; font-size:0.85rem; margin-left:8px;'>🏷️ Bạn đã gán: XẤU LUÔN</span>"
                elif u_rev == "clean":
                    user_badge_html = "<span style='background:#DCFCE7; color:#15803D; padding:4px 10px; border-radius:6px; font-weight:700; font-size:0.85rem; margin-left:8px;'>🏷️ Bạn đã gán: TRONG SẠCH</span>"
                else:
                    user_badge_html = "<span style='background:#FEF3C7; color:#B45309; padding:4px 10px; border-radius:6px; font-weight:700; font-size:0.85rem; margin-left:8px;'>🏷️ Bạn đã gán: CHƯA RÕ</span>"

            # Highlighted comment content (includes newly learned words immediately!)
            all_detected_kws = list(set(combined_matched_words + item.get("user_keywords_list", [])))
            all_detected_emojis = combined_matched_emojis
            comment_html = highlight_comment_text(content_text, all_detected_kws + all_detected_emojis)

            # Accent color for top status bar
            accent_color = "#EF4444" if is_sys_toxic else ("#F59E0B" if is_sys_ambiguous else "#10B981")

            # RENDER THE MAIN FOCUS CARD USING NATIVE STREAMLIT CONTAINER & ST.HTML
            with st.container(border=True):
                # Sleek top color bar
                st.html(f"<div style='height:4px; background:{accent_color}; border-radius:2px; margin-bottom:12px;'></div>")

                col_hdr1, col_hdr2 = st.columns([3, 2])
                with col_hdr1:
                    st.html(
                        f"<div style='font-size:1.05rem; line-height:1.6;'>"
                        f"<b><a href='{author_url}' target='_blank' style='color:#0F172A; text-decoration:none;'>@{author_user}</a></b> "
                        f"<span style='color:#64748B; font-size:0.92rem;'>({author_name})</span> &nbsp; "
                        f"<span style='background:#E0E7FF; color:#3730A3; padding:2px 8px; border-radius:10px; font-size:12px; font-weight:600;'>{c_type_label}</span> &nbsp; "
                        f"<span style='background:#F1F5F9; color:#475569; padding:2px 8px; border-radius:10px; font-size:12px;'>❤️ {likes_count} thích</span>"
                        f"</div>"
                    )
                with col_hdr2:
                    st.html(
                        f"<div style='text-align:right; font-size:0.95rem; line-height:1.6;'>{sys_badge_html} {user_badge_html}</div>"
                    )

                # Large comment content box with guaranteed line wrap
                st.html(
                    f"<div class='comment-large-text'>{comment_html}</div>"
                )

            # Context quote box (Original post context)
            post_content = item.get("post_content") or ""
            post_categories = item.get("post_categories_list") or []
            if post_content:
                with st.expander("📖 Xem bài viết gốc liên quan (Ngữ cảnh)", expanded=False):
                    post_author = item.get("post_author") or ""
                    post_link = item.get("post_url") or ""
                    post_link_html = f"· <a href='{post_link}' target='_blank'>Xem link gốc</a>" if post_link else ""
                    post_cats_str = ", ".join(post_categories) if post_categories else "Chung"
                    st.html(
                        f"<div class='context-quote'>"
                        f"<b>Tác giả bài viết:</b> @{post_author} {post_link_html}<br>"
                        f"<b>Chủ đề:</b> {post_cats_str}<br>"
                        f"<b>Nội dung bài gốc:</b> {html.escape(post_content)}"
                        f"</div>"
                    )

            # 5. Interactive Bad Word Picker (Chọn từ xấu trực tiếp)
            st.markdown("#### 🎯 Chọn từ xấu &amp; Từ lóng độc hại trong bình luận này:")
            candidate_tokens = extract_candidate_words(
                content_text,
                combined_matched_words,
                combined_matched_emojis
            )

            # Pre-select any already marked or matched bad words
            preselected_words = [t for t in (item.get("user_keywords_list") or combined_matched_words or []) if t in candidate_tokens]

            col_picker1, col_picker2 = st.columns([3.2, 1.8])

            with col_picker1:
                if candidate_tokens:
                    selected_pills = st.pills(
                        "👉 Click trực tiếp vào các từ dưới đây để chọn làm từ xấu (Nhấn lại để bỏ chọn):",
                        options=candidate_tokens,
                        default=preselected_words,
                        selection_mode="multi",
                        key=f"pills_select_{item['id']}_{cur_idx}"
                    )
                else:
                    selected_pills = []

            with col_picker2:
                custom_slang = st.text_input(
                    "✍️ Gõ bổ sung từ lóng mới (nếu có):",
                    placeholder="vd: trẩu, ảo tưởng, hãm, cút...",
                    key=f"custom_slang_{item['id']}_{cur_idx}"
                )
                quick_preset = st.selectbox(
                    "⚡ Thêm nhanh từ xấu phổ biến:",
                    ["-- Chọn nhanh để thêm --", "ngu", "chó", "cút", "hãm", "trẩu", "bá khí", "đĩ", "mất dạy", "vô học", "bake", "namky", "ảo tưởng", "bốc phốt"],
                    key=f"quick_preset_{item['id']}_{cur_idx}"
                )

            # 6. Action Buttons (1-Click Fast Labeling)
            st.markdown("#### 🏷️ Gán nhãn cho bình luận này:")
            col_b1, col_b2, col_b3 = st.columns(3)

            # Helper to advance
            def advance_queue():
                if auto_advance:
                    if current_filter_rev != "unreviewed":
                        st.session_state["focus_current_idx"] = min(total_matching - 1, cur_idx + 1)
                    st.rerun()

            with col_b1:
                if st.button("🔴 XẤU LUÔN (Độc hại / Vi phạm)", type="primary", use_container_width=True, key=f"btn_bad_{item['id']}"):
                    all_bad = list(selected_pills or [])
                    if quick_preset and quick_preset != "-- Chọn nhanh để thêm --":
                        all_bad.append(quick_preset)
                    if custom_slang.strip():
                        all_bad.extend([w.strip() for w in custom_slang.split(",") if w.strip()])
                    all_bad = list(set(all_bad))

                    db_manager.update_user_review(comment_id=item["id"], user_review="bad", user_keywords=all_bad)
                    toxic_engine.learn_from_user_evaluation(
                        text=content_text,
                        user_review="bad",
                        new_keywords=all_bad,
                        category="slang",
                        post_context=post_content,
                        topic=", ".join(post_categories)
                    )

                    # Auto-propagate newly learned bad words to all other unreviewed comments in SQLite!
                    propagated_count = db_manager.propagate_learned_keywords(all_bad, toxic_engine)
                    prop_msg = f" và tự động phát hiện cho {propagated_count} bình luận tương tự trong hàng đợi!" if propagated_count > 0 else "!"
                    st.toast(f"🔴 Đã lưu nhãn: XẤU LUÔN! Đã học từ lóng{prop_msg}", icon="⚡")
                    advance_queue()

            with col_b2:
                if st.button("🟡 CHƯA RÕ (Nghi ngờ / Cần theo dõi)", use_container_width=True, key=f"btn_amb_{item['id']}"):
                    all_amb = list(selected_pills or [])
                    if quick_preset and quick_preset != "-- Chọn nhanh để thêm --":
                        all_amb.append(quick_preset)
                    if custom_slang.strip():
                        all_amb.extend([w.strip() for w in custom_slang.split(",") if w.strip()])
                    all_amb = list(set(all_amb))

                    db_manager.update_user_review(comment_id=item["id"], user_review="ambiguous", user_keywords=all_amb)
                    if all_amb:
                        toxic_engine.learn_from_user_evaluation(
                            text=content_text,
                            user_review="ambiguous",
                            new_keywords=all_amb,
                            category="slang",
                            post_context=post_content,
                            topic=", ".join(post_categories)
                        )
                    st.toast("🟡 Đã lưu nhãn: CHƯA RÕ (Nghi ngờ)!")
                    advance_queue()

            with col_b3:
                if st.button("🟢 TRONG SẠCH (Bình thường)", use_container_width=True, key=f"btn_clean_{item['id']}"):
                    db_manager.update_user_review(comment_id=item["id"], user_review="clean", user_keywords=[])
                    toxic_engine.learn_from_user_evaluation(
                        text=content_text,
                        user_review="clean",
                        post_context=post_content,
                        topic=", ".join(post_categories)
                    )
                    st.toast("🟢 Đã lưu nhãn: TRONG SẠCH!")
                    advance_queue()

            # Skip button
            st.write("")
            c_sk1, c_sk2 = st.columns([4, 1])
            with c_sk2:
                if st.button("⏭️ Bỏ qua câu này", use_container_width=True, key=f"skip_btn_{item['id']}"):
                    st.session_state["focus_current_idx"] = min(total_matching - 1, cur_idx + 1)
                    st.rerun()

# TAB 2: DETAILED EXCEL & CSV EXPORT
elif menu == "📥 Xuất dữ liệu Excel & CSV (Fix size / Tự tổng hợp)":
    st.markdown('<div class="main-header">📥 Xuất Dữ Liệu Bình Luận Excel & CSV (Đã Fix Kích Thước Ô)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Hỗ trợ xuất bảng 4 cốt lõi: <b>Nội dung</b>, <b>Điểm đánh giá</b>, <b>Bài viết gốc</b>, <b>Chủ đề bài viết</b> đã được <b>căn chỉnh cố định độ rộng ô và tự động xuống dòng (Wrap Text)</b> để bạn tự đánh giá.</div>', unsafe_allow_html=True)

    export_style = st.radio(
        "Chọn cấu trúc bảng cần xuất:",
        [
            "🎯 BẢNG 4 CỘT CHUẨN ĐỂ TỰ ĐÁNH GIÁ (Đã fix size ô Excel & Wrap text theo yêu cầu)",
            "📑 BẢNG CHI TIẾT ĐẦY ĐỦ THUỘC TÍNH (Dành cho nhà phát triển / AI Fine-tuning)"
        ],
        index=0,
        horizontal=True
    )

    c_cat, c_type = st.columns([2, 1.5])
    with c_cat:
        export_category = st.radio(
            "Chọn nhóm dữ liệu bình luận cần xuất:",
            [
                "📋 TOÀN BỘ BÌNH LUẬN (Đã gắn nhãn Xấu / Chưa rõ / Sạch để tự tổng hợp)",
                "🔴 Chỉ bình luận ĐÁNH GIÁ LÀ XẤU LUÔN (Độc hại rõ ràng)",
                "🟡 Chỉ bình luận CHƯA RÕ (Nghi ngờ / Cần duyệt lại)",
                "🟢 Chỉ bình luận TRONG SẠCH"
            ],
            index=0
        )
    with c_type:
        comment_type_select = st.radio(
            "Phân loại cấu trúc bình luận:",
            [
                "💬 Cả gốc & con (Toàn bộ)",
                "🗨️ Chỉ bình luận gốc",
                "↳ Chỉ bình luận con (Phản hồi)"
            ],
            index=0
        )

    status_code = "all"
    if "XẤU LUÔN" in export_category:
        status_code = "bad"
    elif "CHƯA RÕ" in export_category:
        status_code = "ambiguous"
    elif "TRONG SẠCH" in export_category:
        status_code = "clean"

    type_code = "all"
    if "Chỉ bình luận gốc" in comment_type_select:
        type_code = "root"
    elif "Chỉ bình luận con" in comment_type_select:
        type_code = "reply"

    if "BẢNG 4 CỘT CHUẨN" in export_style:
        # Curated export table
        df_curated = db_manager.get_curated_export_df(
            filter_status=status_code,
            filter_comment_type=type_code,
            limit=None
        )

        st.markdown("### 👁️ Xem trước bảng 4 cột cốt lõi & Tùy chọn Ẩn/Hiện cột")
        if not df_curated.empty:
            all_curated_cols = list(df_curated.columns)

            # Interactive Column Visibility Selector
            with st.expander("🛠️ TÙY CHỌN ẨN / HIỆN CỘT (Cột bị ẩn trên giao diện sẽ KHÔNG xuất hiện trong file Excel/CSV)", expanded=True):
                st.markdown("**Bỏ chọn cột nào thì file Excel / CSV tải về sẽ tự động LOẠI BỎ cột đó:**")
                c_p1, c_p2, c_p3 = st.columns([1.2, 1.4, 1.6])
                with c_p1:
                    if st.button("📋 Chọn tất cả cột", key="btn_all_curated"):
                        st.session_state["curated_cols_sel"] = all_curated_cols
                        st.rerun()
                with c_p2:
                    if st.button("🎯 Chỉ 4 cột cốt lõi", key="btn_4core_curated", help="Nội dung, Điểm đánh giá, Bài viết, Chủ đề bài viết"):
                        st.session_state["curated_cols_sel"] = ["Nội dung", "Điểm đánh giá", "Bài viết", "Chủ đề bài viết"]
                        st.rerun()
                with c_p3:
                    if st.button("🏷️ 4 cột cốt lõi + Tự đánh giá", key="btn_compact_curated"):
                        st.session_state["curated_cols_sel"] = [
                            "Nội dung", "Điểm đánh giá", "Bài viết", "Chủ đề bài viết",
                            "Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)"
                        ]
                        st.rerun()

                default_curated_cols = st.session_state.get("curated_cols_sel", all_curated_cols)
                # Ensure all in default exist in all_curated_cols
                default_curated_cols = [c for c in default_curated_cols if c in all_curated_cols] or all_curated_cols

                chosen_curated_cols = st.multiselect(
                    "Chọn danh sách cột cần xuất ra file:",
                    options=all_curated_cols,
                    default=default_curated_cols,
                    key="curated_cols_multiselect"
                )

            if not chosen_curated_cols:
                st.warning("⚠️ Bạn đã ẩn toàn bộ các cột! Vui lòng chọn ít nhất 1 cột bên trên.")
                chosen_curated_cols = ["Nội dung"]

            df_display = df_curated[chosen_curated_cols]
            st.info(f"Đang hiển thị **{len(df_display)}** dòng và **{len(chosen_curated_cols)}** cột đã chọn. File Excel xuất ra sẽ chỉ có đúng các cột này!")
            st.dataframe(df_display.head(60), use_container_width=True, height=380)

            st.divider()
            c_btn1, c_btn2 = st.columns(2)

            with c_btn1:
                curated_xlsx = exporter.export_curated_excel(
                    filter_status=status_code,
                    filter_comment_type=type_code,
                    columns=chosen_curated_cols
                )
                with open(curated_xlsx, "rb") as f:
                    st.download_button(
                        label=f"📊 TẢI EXCEL (.XLSX) CHỨA {len(chosen_curated_cols)} CỘT ĐÃ CHỌN",
                        data=f,
                        file_name=curated_xlsx.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )
                st.caption(f"✅ Đã fix size ô, wrap text và **chỉ xuất {len(chosen_curated_cols)} cột**: {', '.join(chosen_curated_cols)}.")

            with c_btn2:
                curated_csv = exporter.export_curated_csv(
                    filter_status=status_code,
                    filter_comment_type=type_code,
                    columns=chosen_curated_cols
                )
                with open(curated_csv, "rb") as f:
                    st.download_button(
                        label=f"📄 TẢI CSV CHỨA {len(chosen_curated_cols)} CỘT ĐÃ CHỌN",
                        data=f,
                        file_name=curated_csv.name,
                        mime="text/csv",
                        use_container_width=True
                    )
                st.caption("Chuẩn mã UTF-8-BOM: Mở trực tiếp bằng Microsoft Excel (Windows) không lỗi font.")
        else:
            st.warning("Hiện tại chưa có bình luận nào thuộc nhóm này trong CSDL.")

    else:
        # Detailed technical table
        include_links = st.checkbox("🔗 Bổ sung cột Link & Parent ID", value=False)
        df_comments = db_manager.get_comments_export_df(
            filter_status=status_code,
            filter_comment_type=type_code,
            include_links=include_links,
            limit=None
        )

        st.markdown("### 👁️ Xem trước bảng chi tiết đầy đủ & Tùy chọn Ẩn/Hiện cột")
        if not df_comments.empty:
            all_detail_cols = list(df_comments.columns)
            with st.expander("🛠️ TÙY CHỌN ẨN / HIỆN CỘT (Cột bị ẩn sẽ KHÔNG xuất hiện trong file Excel/CSV)", expanded=True):
                chosen_detail_cols = st.multiselect(
                    "Chọn các cột bạn muốn hiển thị và xuất:",
                    options=all_detail_cols,
                    default=all_detail_cols,
                    key="detail_cols_multiselect"
                )
            if not chosen_detail_cols:
                chosen_detail_cols = all_detail_cols

            df_detail_display = df_comments[chosen_detail_cols]
            st.info(f"Đang có **{len(df_detail_display)}** dòng và **{len(chosen_detail_cols)}** cột sẵn sàng xuất.")
            st.dataframe(df_detail_display.head(60), use_container_width=True, height=360)

            st.divider()
            c_btn1, c_btn2, c_btn3 = st.columns(3)

            with c_btn1:
                csv_path = exporter.export_comments_csv(
                    filter_status=status_code,
                    filter_comment_type=type_code,
                    include_links=include_links,
                    columns=chosen_detail_cols
                )
                with open(csv_path, "rb") as f:
                    st.download_button(
                        label=f"📄 TẢI CSV ({len(chosen_detail_cols)} CỘT)",
                        data=f,
                        file_name=csv_path.name,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )

            with c_btn2:
                excel_path = exporter.export_to_excel(
                    table_type="comments",
                    toxic_only=(status_code != "all"),
                    columns=chosen_detail_cols
                )
                with open(excel_path, "rb") as f:
                    st.download_button(
                        label=f"📊 TẢI EXCEL TÔ MÀU ({len(chosen_detail_cols)} CỘT)",
                        data=f,
                        file_name=excel_path.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            with c_btn3:
                json_path = exporter.export_to_json(table_type="comments", toxic_only=(status_code != "all"))
                with open(json_path, "rb") as f:
                    st.download_button(
                        label="📦 TẢI JSON (AI DATASET)",
                        data=f,
                        file_name=json_path.name,
                        mime="application/json",
                        use_container_width=True
                    )
        else:
            st.warning("Hiện tại chưa có bình luận nào thuộc nhóm này trong CSDL.")

# TAB 3: DATA & ACTIVE LEARNING
elif menu == "📋 Dữ liệu & Tự đánh giá (Học máy)":
    st.markdown('<div class="main-header">📋 Dữ Liệu, Kiểm Duyệt & Vòng Lặp Học Máy (Active Learning)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Sau khi bạn tự đánh giá, hệ thống sẽ <b>cập nhật CSDL</b>, <b>trích xuất từ lóng mới</b> và <b>nạp lại vào từ điển JSON</b> để dần dần tự động hóa!</div>', unsafe_allow_html=True)

    # 0. PURGE FOREIGN LANGUAGE RECORDS
    with st.expander("🧹 Dọn dẹp dữ liệu tiếng Trung, Nhật, Hàn... trong CSDL", expanded=False):
        st.markdown("""
        Quét toàn bộ CSDL và **xóa các bình luận / bài đăng** hoàn toàn bằng ngôn ngữ nước ngoài
        (tiếng Trung 🇨🇳, Nhật 🇯🇵, Hàn 🇰🇷, Thái, Ả Rập, Nga...).
        Các bình luận tiếng Việt/Anh **có lẫn** vài ký tự ngoại ngữ sẽ được **làm sạch tự động** (không xóa).
        """)
        if st.button("🧹 BẮT ĐẦU DỌN DẸP DỮ LIỆU NGOẠI NGỮ", type="secondary", use_container_width=True, key="purge_foreign_btn"):
            with st.spinner("Đang quét và dọn dẹp CSDL..."):
                try:
                    purge_result = db_manager.purge_foreign_language_records()
                    st.success(
                        f"✅ Dọn dẹp hoàn tất!\n\n"
                        f"- **Đã xóa** {purge_result['purged_comments']} bình luận hoàn toàn tiếng nước ngoài\n"
                        f"- **Đã xóa** {purge_result['purged_posts']} bài đăng hoàn toàn tiếng nước ngoài\n"
                        f"- **Đã làm sạch** {purge_result['cleaned_comments']} bình luận có ký tự ngoại ngữ lẫn lộn (đã giữ lại phần Việt/Anh)"
                    )
                    if purge_result['purged_comments'] == 0 and purge_result['purged_posts'] == 0 and purge_result['cleaned_comments'] == 0:
                        st.info("CSDL đã sạch — Không tìm thấy dữ liệu tiếng nước ngoài nào!")
                except Exception as e:
                    st.error(f"Lỗi khi dọn dẹp: {e}")

    # 0b. CLEAR ALL DATA
    with st.expander("🗑️ Xóa toàn bộ dữ liệu trong CSDL", expanded=False):
        _cur_stats = db_manager.get_stats()
        st.markdown(f"""
        <div style='background:#FEF2F2; border:1.5px solid #F87171; border-radius:8px; padding:10px 14px; margin-bottom:10px;'>
            ⚠️ <b>CẢNH BÁO NGHIÊM TRỌNG</b><br>
            Thao tác này sẽ <b>XÓA VĨNH VIỄN TOÀN BỘ</b> dữ liệu trong cơ sở dữ liệu và <b>KHÔNG THỂ HOÀN TÁC</b>.<br>
            Hiện đang có: <b>{_cur_stats['total_comments']}</b> bình luận &amp; <b>{_cur_stats['total_posts']}</b> bài đăng sẽ bị xóa hết.
        </div>
        """, unsafe_allow_html=True)

        # Two-step confirmation: checkbox + button
        confirm_clear = st.checkbox(
            "✅ Tôi hiểu rằng hành động này KHÔNG THỂ HOÀN TÁC và muốn xóa toàn bộ dữ liệu",
            key="confirm_clear_all_cb"
        )
        if confirm_clear:
            if st.button(
                f"🗑️ XÓA HẾT {_cur_stats['total_comments']} BÌNH LUẬN & {_cur_stats['total_posts']} BÀI ĐĂNG",
                type="primary",
                use_container_width=True,
                key="clear_all_data_btn"
            ):
                with st.spinner("Đang xóa toàn bộ dữ liệu..."):
                    try:
                        clear_result = db_manager.clear_all_data()
                        st.success(
                            f"🗑️ Đã xóa toàn bộ dữ liệu thành công!\n\n"
                            f"- Đã xóa **{clear_result['deleted_comments']}** bình luận\n"
                            f"- Đã xóa **{clear_result['deleted_posts']}** bài đăng\n"
                            f"- Đã xóa **{clear_result['deleted_sessions']}** phiên cào\n\n"
                            f"CSDL hiện đang trống. Hãy bắt đầu thu thập dữ liệu mới!"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xóa dữ liệu: {e}")
        else:
            st.caption("☝️ Tích vào ô xác nhận bên trên để kích hoạt nút xóa.")

    # 1. FILE RE-INGESTION / IMPORT
    with st.expander("📥 1. NẠP FILE EXCEL / CSV BẠN ĐÃ TỰ ĐÁNH GIÁ (DẠY HỆ THỐNG TỰ ĐỘNG HÓA)", expanded=False):
        st.markdown("""
        **Hướng dẫn:**
        1. Tải file Excel/CSV từ tab **📥 Xuất dữ liệu** về máy.
        2. Mở file bằng Microsoft Excel, điền cột **Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)** và bổ sung các từ lóng mới phát hiện vào cột **Từ lóng mới bổ sung (nếu có)**.
        3. Tải file đã đánh giá lên đây để hệ thống tự động học và nạp vào từ điển!
        """)
        uploaded_file = st.file_uploader("Chọn file Excel (.xlsx) hoặc CSV (.csv) đã tự đánh giá:", type=["xlsx", "xls", "csv"])
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".xlsx") or uploaded_file.name.endswith(".xls"):
                    df_up = pd.read_excel(uploaded_file)
                else:
                    df_up = pd.read_csv(uploaded_file)
                st.caption(f"Đã đọc thành công file với **{len(df_up)}** dòng.")

                if st.button("🚀 TIẾN HÀNH ĐỒNG BỘ CSDL & NẠP TỪ LÓNG MỚI VÀO JSON", type="primary"):
                    col_id = next((c for c in ["Mã ID", "id", "comment_id", "ID"] if c in df_up.columns), None)
                    col_review = next((c for c in ["Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)", "Tự đánh giá của bạn", "user_review", "Đánh giá"] if c in df_up.columns), None)
                    col_content = next((c for c in ["Nội dung", "content", "Nội dung bình luận"] if c in df_up.columns), None)
                    col_post = "Bài viết" if "Bài viết" in df_up.columns else None
                    col_topic = "Chủ đề bài viết" if "Chủ đề bài viết" in df_up.columns else None
                    col_new_words = next((c for c in ["Từ lóng mới bổ sung (nếu có)", "Từ lóng mới", "new_keywords"] if c in df_up.columns), None)

                    if not col_id or not col_review:
                        st.error("File tải lên thiếu cột 'Mã ID' hoặc 'Tự đánh giá của bạn'. Vui lòng dùng đúng file mẫu được xuất từ hệ thống!")
                    else:
                        updated_count = 0
                        added_kw_list = []
                        for _, row in df_up.iterrows():
                            rev_val = str(row.get(col_review, "")).strip()
                            if not rev_val or rev_val.lower() == "nan":
                                continue

                            rev_clean = rev_val.lower()
                            if "xấu" in rev_clean or "bad" in rev_clean or "độc" in rev_clean:
                                u_tag = "bad"
                            elif "sạch" in rev_clean or "clean" in rev_clean:
                                u_tag = "clean"
                            elif "chưa rõ" in rev_clean or "ambiguous" in rev_clean or "nghi" in rev_clean:
                                u_tag = "ambiguous"
                            else:
                                u_tag = rev_val

                            c_id = str(row.get(col_id, "")).strip()
                            c_text = str(row.get(col_content, "")).strip() if col_content else ""
                            p_context = str(row.get(col_post, "")).strip() if col_post else ""
                            c_topic = str(row.get(col_topic, "")).strip() if col_topic else ""
                            n_str = str(row.get(col_new_words, "")).strip() if col_new_words else ""
                            n_kws = [w.strip() for w in n_str.split(",") if w.strip() and w.strip().lower() != "nan"]

                            db_manager.update_user_review(comment_id=c_id, user_review=u_tag, user_keywords=n_kws)
                            learn_res = toxic_engine.learn_from_user_evaluation(
                                text=c_text,
                                user_review=u_tag,
                                new_keywords=n_kws,
                                post_context=p_context,
                                topic=c_topic
                            )
                            if learn_res.get("added_keywords"):
                                added_kw_list.extend(learn_res["added_keywords"])
                            updated_count += 1

                        st.success(f"🎉 Hoàn tất đồng bộ! Đã cập nhật **{updated_count}** bình luận được bạn tự đánh giá vào CSDL.")
                        if added_kw_list:
                            unique_kws = list(set(added_kw_list))
                            st.info(f"✨ Đã tự động nạp thêm **{len(unique_kws)}** từ lóng mới vào từ điển `config/toxic_keywords.json`: **{', '.join(unique_kws)}**")
                        st.info("📦 Mẫu dữ liệu đã được lưu vào `data/training_dataset.json` để sẵn sàng cho tự động hóa mô hình AI.")
            except Exception as e:
                st.error(f"Lỗi khi đọc file: {e}")

    # 2. DIRECT INTERACTIVE EVALUATION
    with st.expander("✍️ 2. TỰ ĐÁNH GIÁ TRỰC TIẾP TỪNG BÌNH LUẬN TRÊN GIAO DIỆN", expanded=False):
        st.info("💡 **Gợi ý:** Bạn có thể chuyển sang mục **⚡ Gán nhãn từng bình luận (Siêu tốc)** trên menu bên trái để đọc bình luận chữ to rõ, bấm chọn từ xấu trực tiếp và gán nhãn 1-click tự động chuyển tiếp nhanh hơn gấp 10 lần!")
        if st.button("🚀 MỞ GIAO DIỆN GÁN NHÃN TỪNG CÂU SIÊU TỐC", type="primary", key="open_focus_from_sec2"):
            st.session_state["main_menu_choice"] = "⚡ Gán nhãn từng bình luận (Siêu tốc)"
            st.rerun()
        st.divider()

        sample_df = db_manager.get_curated_export_df(filter_status="all", limit=50)
        if not sample_df.empty:
            id_options = sample_df["Mã ID"].tolist()
            selected_id = st.selectbox("Chọn Mã ID bình luận cần đánh giá:", id_options)
            chosen_row = sample_df[sample_df["Mã ID"] == selected_id].iloc[0]

            col_detail1, col_detail2 = st.columns(2)
            with col_detail1:
                st.markdown(f"**Nội dung bình luận:**\n> {chosen_row['Nội dung']}")
                st.caption(f"Hệ thống chấm: **{chosen_row['Điểm đánh giá']}**")
            with col_detail2:
                st.markdown(f"**Bài viết gốc:**\n> {str(chosen_row['Bài viết'])[:160]}...")
                st.caption(f"Chủ đề: **{chosen_row['Chủ đề bài viết']}**")

            c_eval1, c_eval2 = st.columns([1.5, 2])
            with c_eval1:
                eval_choice = st.radio(
                    "Đánh giá của bạn:",
                    ["🔴 Xấu luôn (Độc hại rõ ràng)", "🟡 Chưa rõ (Nghi ngờ / Cần theo dõi)", "🟢 Trong sạch (Bình thường)"]
                )
            with c_eval2:
                new_slang_input = st.text_input(
                    "Bổ sung từ lóng mới phát hiện (cách nhau bởi dấu phẩy):",
                    placeholder="vd: trẩu, ảo tưởng, bốc phốt, hãm..."
                )

            if st.button("💾 LƯU ĐÁNH GIÁ & DẠY HỆ THỐNG", type="primary"):
                tag = "bad" if "Xấu luôn" in eval_choice else ("ambiguous" if "Chưa rõ" in eval_choice else "clean")
                new_kws = [w.strip() for w in new_slang_input.split(",") if w.strip()]

                db_manager.update_user_review(comment_id=selected_id, user_review=tag, user_keywords=new_kws)
                learn_res = toxic_engine.learn_from_user_evaluation(
                    text=chosen_row["Nội dung"],
                    user_review=tag,
                    new_keywords=new_kws,
                    post_context=str(chosen_row["Bài viết"]),
                    topic=str(chosen_row["Chủ đề bài viết"])
                )
                st.success(f"✅ Đã lưu đánh giá cho bình luận `{selected_id}`!")
                if learn_res.get("added_keywords"):
                    st.info(f"✨ Đã bổ sung từ lóng mới: {learn_res['added_keywords']} vào `config/toxic_keywords.json`!")
                st.rerun()
        else:
            st.info("Chưa có bình luận nào trong CSDL để đánh giá.")

    # 3. FULL COMMENTS TABLE & FILTERS
    st.markdown("### 👁️ 3. Bảng Kiểm Duyệt & Tra Cứu Bình Luận Chi Tiết")
    st.markdown("""
    <div style='background: linear-gradient(90deg, #EFF6FF 0%, #EEF2FF 100%); border: 1.5px solid #6366F1; border-radius: 10px; padding: 12px 18px; margin-bottom: 12px;'>
        <div style='color: #4338CA; font-weight: 700; font-size: 15px;'>⚡ Bạn thấy khó đọc bình luận dài trên bảng và mỏi mắt vì phải double-click?</div>
        <div style='color: #475569; font-size: 13px; margin-top: 3px;'>
            Chuyển ngay sang <b>Chế độ Thẻ từng bình luận</b>: Chữ to rõ 100%, không bị cắt dòng, tự động bôi đỏ từ nhạy cảm, bấm chọn từ xấu trực tiếp &amp; gán nhãn 1-click siêu tốc!
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("⚡ CHUYỂN SANG CHẾ ĐỘ GÁN NHÃN TỪNG BÌNH LUẬN (FOCUS VIEW)", type="primary", use_container_width=True, key="switch_to_focus_banner_btn"):
        st.session_state["main_menu_choice"] = "⚡ Gán nhãn từng bình luận (Siêu tốc)"
        st.rerun()
    st.write("")
    c1, c2, c3, c4 = st.columns([2, 1.5, 1, 2])
    with c1:
        status_filter = st.selectbox(
            "Lọc theo đánh giá hệ thống:",
            ["Tất cả bình luận", "Chỉ bình luận Xấu luôn (Rõ ràng)", "Chỉ bình luận Chưa rõ (Nghi ngờ)", "Bình luận Trong sạch"]
        )
    with c2:
        type_filter = st.selectbox(
            "Phân loại cấu trúc:",
            ["Tất cả (Gốc & Con)", "Chỉ bình luận gốc", "Chỉ bình luận con (Phản hồi)"]
        )
    with c3:
        include_links_mod = st.checkbox("Hiện Link & ID cha", value=False)
    with c4:
        search_kw = st.text_input("Tìm kiếm theo nội dung / tác giả / từ lóng:", "")

    f_map = {
        "Tất cả bình luận": "all",
        "Chỉ bình luận Xấu luôn (Rõ ràng)": "bad",
        "Chỉ bình luận Chưa rõ (Nghi ngờ)": "ambiguous",
        "Bình luận Trong sạch": "clean"
    }
    t_map = {
        "Tất cả (Gốc & Con)": "all",
        "Chỉ bình luận gốc": "root",
        "Chỉ bình luận con (Phản hồi)": "reply"
    }
    df = db_manager.get_comments_export_df(
        filter_status=f_map[status_filter],
        filter_comment_type=t_map[type_filter],
        include_links=include_links_mod,
        limit=None
    )

    if not df.empty:
        if search_kw:
            mask = df.astype(str).apply(lambda row: row.str.contains(search_kw, case=False, na=False)).any(axis=1)
            df = df[mask]

        with st.expander("🛠️ Tùy chọn ẩn / hiện cột trên bảng kiểm duyệt:", expanded=False):
            tab3_selected_cols = st.multiselect(
                "Chọn các cột muốn hiển thị:",
                options=list(df.columns),
                default=list(df.columns),
                key="tab3_cols_multiselect"
            )

        df_show = df[tab3_selected_cols] if tab3_selected_cols else df
        st.info(f"Hiển thị {len(df_show)} dòng kết quả ({len(df_show.columns)} cột).")
        st.dataframe(df_show, use_container_width=True, height=520)
    else:
        st.info("Chưa có dữ liệu phù hợp.")

# TAB 4: ANALYTICS & CHARTS
elif menu == "📊 Thống kê & Phân tích":
    st.markdown('<div class="main-header">📊 Thống Kê & Phân Tích Dữ Liệu Xúc Phạm</div>', unsafe_allow_html=True)
    stats = db_manager.get_stats()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Tổng cmt & bài", stats["total_items"])
    m2.metric("Bình luận gốc", stats.get("total_root_comments", 0))
    m3.metric("Bình luận con (Reply)", stats.get("total_child_comments", 0))
    m4.metric("Bình luận vi phạm", f"{stats['toxic_comments']} / {stats['total_comments']}")
    m5.metric("Bài đăng vi phạm", f"{stats['toxic_posts']} / {stats['total_posts']}")

    st.divider()
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("🔥 Top Từ Lóng / Xúc Phạm Xuất Hiện Nhiều Nhất")
        top_words = db_manager.get_top_toxic_words(14)
        if top_words:
            df_words = pd.DataFrame(top_words)
            chart = alt.Chart(df_words).mark_bar(color="#EF4444").encode(
                x=alt.X('count:Q', title="Số lần xuất hiện"),
                y=alt.Y('word:N', sort='-x', title="Từ ngữ / Từ lóng"),
                tooltip=['word', 'count']
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu từ ngữ vi phạm.")

    with col_right:
        st.subheader("👤 Top Tài Khoản Thường Xuyên Vi Phạm")
        top_users = db_manager.get_top_toxic_users(8)
        if top_users:
            df_users = pd.DataFrame(top_users)
            chart_users = alt.Chart(df_users).mark_bar(color="#6366F1").encode(
                x=alt.X('toxic_count:Q', title="Số vi phạm"),
                y=alt.Y('author_username:N', sort='-x', title="Tài khoản @"),
                tooltip=['author_username', 'toxic_count']
            ).properties(height=400)
            st.altair_chart(chart_users, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu tài khoản vi phạm.")

# TAB 5: QUICK SCANNER
elif menu == "🔍 Kiểm tra văn bản & Icon":
    st.markdown('<div class="main-header">🔍 Kiểm Tra Văn Bản, Từ Lóng & Icon Nhạy Cảm</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Kiểm tra ngay câu văn có dấu, không dấu, từ lóng teencode hoặc icon xúc phạm</div>', unsafe_allow_html=True)

    input_text = st.text_area(
        "Nhập nội dung cần phân tích:",
        value="Thằng bake này ngu như bò cút đi 🖕 🤡",
        height=120
    )

    if st.button("🔎 PHÂN TÍCH NGAY", type="primary"):
        res = toxic_engine.analyze(input_text)
        col1, col2, col3 = st.columns(3)
        with col1:
            if res.is_toxic:
                st.error("⚠️ PHÁT HIỆN CÓ TỪ NGỮ / ICON ĐỘC HẠI")
            else:
                st.success("✅ VĂN BẢN TRONG SẠCH")
        with col2:
            st.metric("Điểm Toxic Score", f"{res.score} / 1.0")
        with col3:
            st.metric("Mức độ nghiêm trọng", res.severity_vi)

        st.markdown("### Chi tiết phát hiện:")
        st.write(f"- **Từ lóng & xúc phạm (có dấu & không dấu):** `{', '.join(res.matched_words) if res.matched_words else 'Không có'}`")
        st.write(f"- **Icon nhạy cảm bắt gặp:** `{', '.join(res.matched_emojis) if res.matched_emojis else 'Không có'}`")
        st.write(f"- **Nhóm vi phạm:** `{', '.join(res.category_names) if res.category_names else 'Không có'}`")

# TAB 6: DICTIONARY MANAGER
elif menu == "📚 Từ điển Từ lóng & Icon":
    st.markdown('<div class="main-header">📚 Quản Lý Từ Điển Từ Lóng & Icon Nhạy Cảm</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Hệ thống từ điển đa tầng: Từ lóng bạn gán nhãn (Active Learning), từ khóa hệ thống và emoji vi phạm</div>', unsafe_allow_html=True)

    dict_tab0, dict_tab1, dict_tab2 = st.tabs([
        "🔥 Từ lóng bạn gán nhãn (Active Learning)",
        "🔍 Tra cứu & Quản lý tất cả danh mục",
        "🎭 Biểu tượng Icon / Emoji nhạy cảm"
    ])

    cats = toxic_engine.categories_data

    # SUB-TAB 0: USER LEARNED & ACTIVE LEARNING
    with dict_tab0:
        st.markdown("### 🧠 Danh sách từ lóng được thu thập từ quá trình gán nhãn")
        st.markdown(
            "Mỗi khi bạn bấm **🔴 XẤU LUÔN** hoặc **🟡 CHƯA RÕ** và chọn/xác nhận từ xấu trong phần Focus Review, "
            "hệ thống sẽ tự động lưu từ lóng đó vào đây và lập tức áp dụng cho tất cả các bình luận tương tự về sau."
        )

        learned_list = toxic_engine.get_user_learned_keywords()

        col_m1, col_m2, col_m3 = st.columns([1.5, 1.5, 2])
        with col_m1:
            st.metric("Tổng từ lóng đã học / gán nhãn", f"{len(learned_list)} từ")
        with col_m2:
            slang_count = len(cats.get("slang", {}).get("words", []))
            st.metric("Từ lóng trong danh mục Slang", f"{slang_count} từ")
        with col_m3:
            st.write("")
            if st.button("⚡ Quét & Cập nhật lại toàn bộ CSDL", type="primary", help="Áp dụng toàn bộ từ lóng mới nhất cho tất cả bình luận chưa duyệt trong database"):
                with st.spinner("Đang quét và cập nhật lại toàn bộ bình luận..."):
                    updated_c = db_manager.reanalyze_all_unreviewed_comments(toxic_engine)
                    st.success(f"✅ Đã quét xong! Cập nhật {updated_c} bình luận vi phạm theo từ điển mới.")
                    st.rerun()

        if learned_list:
            df_learned = pd.DataFrame(learned_list)
            df_learned.columns = ["Từ lóng / Cụm từ", "Số lần gán nhãn", "Thời điểm ghi nhận", "Ngữ cảnh bình luận mẫu"]
            st.dataframe(df_learned, use_container_width=True, height=350)

            # Option to delete / unlearn a keyword
            st.markdown("#### 🗑️ Xóa hoặc hủy học từ khóa nếu bấm nhầm")
            c_del1, c_del2 = st.columns([3, 1])
            with c_del1:
                word_to_del = st.selectbox(
                    "Chọn từ khóa muốn xóa khỏi từ điển học máy:",
                    [item["keyword"] for item in learned_list]
                )
            with c_del2:
                st.write("")
                st.write("")
                if st.button("Xóa từ này", type="secondary"):
                    if toxic_engine.remove_keyword(word_to_del):
                        toxic_engine.save_dictionary()
                        st.success(f"Đã xóa '{word_to_del}' khỏi từ điển.")
                        st.rerun()
                    else:
                        st.error("Không tìm thấy từ để xóa.")
        else:
            st.info("Chưa có từ lóng nào được học từ việc gán nhãn. Hãy sang mục Focus Review để bắt đầu gán nhãn!")

    # SUB-TAB 1: ALL CATEGORIES & SEARCH
    with dict_tab1:
        st.markdown("### 🔍 Tra cứu nhanh từ khóa")
        search_kw = st.text_input("Nhập từ khóa cần kiểm tra xem đã có trong từ điển chưa (ví dụ: md, cút, bake, hãm...):")
        if search_kw.strip():
            matches = toxic_engine.search_keywords(search_kw.strip())
            if matches:
                st.success(f"Tìm thấy **{len(matches)}** kết quả phù hợp với `{search_kw.strip()}`:")
                df_matches = pd.DataFrame(matches)
                df_matches.columns = ["Từ khóa", "Mã nhóm", "Tên danh mục vi phạm", "Hệ số nghiêm trọng"]
                st.dataframe(df_matches, use_container_width=True)
            else:
                st.warning(f"Không tìm thấy từ khóa nào chứa `{search_kw.strip()}` trong từ điển hiện tại.")

        st.markdown("---")
        st.markdown("### 📂 Duyệt từ điển theo danh mục")

        cat_keys = list(cats.keys())
        # Default index to 'slang' if available
        default_idx = cat_keys.index("slang") if "slang" in cat_keys else 0
        selected_cat = st.selectbox(
            "Chọn danh mục vi phạm:",
            cat_keys,
            index=default_idx,
            format_func=lambda c: f"{cats[c].get('name_vi', c)} ({len(cats[c].get('words', []))} từ)"
        )

        words_in_cat = cats[selected_cat].get("words", [])
        st.write(f"Hiện có **{len(words_in_cat)}** từ ngữ/từ lóng trong nhóm này (bao gồm cả dạng có dấu, không dấu và viết tắt):")

        # Display as clean tag chips
        if words_in_cat:
            tags_html = " ".join([
                f"<span style='display:inline-block; background:#1e293b; color:#38bdf8; border:1px solid #334155; padding:4px 10px; border-radius:8px; margin:3px; font-size:13px; font-family: monospace;'>{w}</span>"
                for w in words_in_cat
            ])
            st.markdown(
                f"<div style='max-height: 220px; overflow-y: auto; padding: 12px; background: #0f172a; border-radius: 8px; border: 1px solid #1e293b; margin-bottom: 15px;'>{tags_html}</div>",
                unsafe_allow_html=True
            )

        with st.expander("📋 Xem danh sách dạng văn bản (để sao chép)"):
            st.text_area("Toàn bộ từ khóa trong nhóm:", value=", ".join(words_in_cat), height=140, disabled=True)

        st.markdown("#### ➕ Thêm từ khóa mới vào nhóm này")
        c_add1, c_add2 = st.columns([3, 1])
        with c_add1:
            new_word = st.text_input("Nhập từ lóng / từ khóa mới:", key="add_new_kw_input")
        with c_add2:
            st.write("")
            st.write("")
            if st.button("Thêm vào từ điển", key="btn_add_kw", type="primary"):
                w_clean = new_word.strip()
                if w_clean:
                    if toxic_engine.add_keyword(w_clean, selected_cat):
                        toxic_engine.save_dictionary()
                        # Automatically propagate to database
                        db_manager.propagate_learned_keywords([w_clean], toxic_engine)
                        st.success(f"Đã thêm thành công: '{w_clean}' vào nhóm {selected_cat} và cập nhật CSDL!")
                        st.rerun()
                    else:
                        st.warning("Từ này đã tồn tại trong danh sách.")

    # SUB-TAB 2: EMOJIS
    with dict_tab2:
        st.markdown("### 🎭 Biểu tượng cảm xúc (Emoji / Icon) nhạy cảm")
        st.write("Các biểu tượng cảm xúc (Emoji/Icon) được dùng trong ngữ cảnh lăng mạ, xúc phạm danh dự, miệt thị vùng miền hoặc bạo lực mạng:")
        emojis_list = []
        for e_char, e_info in toxic_engine.emojis_data.items():
            emojis_list.append({
                "Biểu tượng": e_char,
                "Ý nghĩa / Ngữ cảnh vi phạm": e_info.get("label", ""),
                "Nhóm vi phạm": cats.get(e_info.get("category", ""), {}).get("name_vi", e_info.get("category", "")),
                "Điểm trọng số": e_info.get("weight", 0.5)
            })
        st.dataframe(pd.DataFrame(emojis_list), use_container_width=True, height=400)
