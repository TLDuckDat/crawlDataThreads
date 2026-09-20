import re
import hashlib
from typing import List, Dict, Any, Optional

EXPAND_MORE_BUTTONS_JS = """
return (() => {
    let clicked = 0;
    const candidates = document.querySelectorAll('div[role="button"], span, button, a[role="button"]');
    for (const el of candidates) {
        // Do not click buttons inside login or modal dialogs
        if (el.closest('div[role="dialog"], [aria-modal="true"], [data-dialog="true"]')) {
            continue;
        }
        // Never click menu popups or left sidebar navigation items
        if (el.getAttribute('aria-haspopup') === 'menu') {
            continue;
        }
        const rect = el.getBoundingClientRect();
        if (rect.left < 200 || rect.width === 0 || rect.height === 0) {
            continue;
        }

        const text = (el.innerText || "").trim().toLowerCase();
        const aria = (el.getAttribute('aria-label') || "").toLowerCase();
        
        const isExpand = (
            text === "xem thêm" || 
            text === "view more" || 
            text.includes("xem thêm câu trả lời") ||
            text.includes("xem câu trả lời") ||
            text.includes("câu trả lời khác") ||
            text.includes("xem thêm phản hồi") ||
            text.includes("xem phản hồi") ||
            text.includes("phản hồi khác") ||
            text.includes("show replies") ||
            text.includes("show reply") ||
            text.includes("view replies") ||
            text.includes("view reply") ||
            text.includes("view more replies") ||
            text.includes("more replies") ||
            /\\d+\\s*(câu trả lời|phản hồi|replies|reply)/i.test(text) ||
            aria.includes("view replies") ||
            aria.includes("show replies") ||
            aria.includes("xem câu trả lời") ||
            aria.includes("xem phản hồi")
        );

        if (isExpand) {
            try {
                el.click();
                clicked++;
            } catch (err) {}
        }
    }
    return clicked;
})();
"""

SCROLL_FEED_JS = """
return (() => {
    // Scroll container in Threads: check #scrollview or window
    const scrollContainer = document.getElementById('scrollview') || document.documentElement;

    // Scroll visible cards in Threads
    const items = Array.from(document.querySelectorAll('div[data-pressable-container="true"]')).filter(el => {
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && rect.left >= 200;
    });

    if (items.length > 0) {
        items[items.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
    }

    if (scrollContainer && scrollContainer !== document.documentElement) {
        scrollContainer.scrollTop += 1000;
    }
    window.scrollBy(0, 1000);

    return {
        itemsCount: items.length
    };
})();
"""

CHECK_LOGIN_WALL_JS = """
return (() => {
    const dialog = document.querySelector('div[role="dialog"], [aria-modal="true"]');
    if (!dialog) return false;
    const text = (dialog.innerText || "").toLowerCase();
    return (
        text.includes("say more with threads") || 
        text.includes("continue with instagram") || 
        text.includes("tiếp tục bằng instagram") || 
        text.includes("tham gia threads để chia sẻ") ||
        text.includes("join threads to share thoughts")
    );
})();
"""

EXTRACT_THREADS_DATA_JS = """
return (() => {
    const results = [];
    const seenTexts = new Set();
    
    // Find all article or container cards in Threads feed/post page (excluding menu popups)
    const elements = document.querySelectorAll('div[data-pressable-container="true"], div[role="article"]');
    
    elements.forEach((el, index) => {
        // Skip hidden, collapsed, or left-sidebar elements
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0 || rect.left < 200 || el.offsetParent === null) {
            return;
        }
        if (window.getComputedStyle(el).display === 'none' || window.getComputedStyle(el).visibility === 'hidden') {
            return;
        }

        // Skip anything inside a dialog/modal (such as the guest login wall)
        if (el.closest('div[role="dialog"], [aria-modal="true"], div[data-dialog="true"]')) {
            return;
        }

        // Find username & author profile
        let username = "";
        let authorName = "";
        let authorProfileUrl = "";
        const userLink = el.querySelector('a[href^="/@"], a[href*="threads.net/@"], a[href*="threads.com/@"]');
        if (userLink) {
            const href = userLink.getAttribute('href') || "";
            const match = href.match(/@([^/?#]+)/);
            if (match) {
                username = match[1];
                authorProfileUrl = `https://www.threads.net/@${username}`;
            }
            authorName = (userLink.innerText || "").trim();
        }
        
        // Find post or comment link
        let itemUrl = "";
        const postLink = el.querySelector('a[href*="/post/"]');
        if (postLink) {
            itemUrl = postLink.href;
        }
        
        // Find timestamp
        let timeStr = "";
        const timeEl = el.querySelector('time');
        if (timeEl) {
            timeStr = timeEl.getAttribute('datetime') || timeEl.innerText || "";
        } else if (postLink) {
            timeStr = (postLink.innerText || "").trim();
        }
        
        // Find Likes count
        let likes = 0;
        const buttons = el.querySelectorAll('div[role="button"], button');
        for (const btn of buttons) {
            if (btn.getAttribute('aria-haspopup') === 'menu') continue;
            const btnText = (btn.innerText || "").trim();
            const match = btnText.match(/^(\\d+(\\.\\d+)?[KMB]?)$/i);
            if (match) {
                let numStr = match[1].toUpperCase();
                if (numStr.endsWith('K')) likes = Math.round(parseFloat(numStr) * 1000);
                else if (numStr.endsWith('M')) likes = Math.round(parseFloat(numStr) * 1000000);
                else likes = parseInt(numStr.replace(/[,.]/g, ''), 10) || 0;
                break;
            }
        }
        if (!likes) {
            const allText = el.innerText || "";
            const likeMatch = allText.match(/(\\d+[\\d,.]*)\\s*(lượt thích|thích|likes?)/i);
            if (likeMatch) {
                const rawNum = likeMatch[1].replace(/[,.]/g, '');
                likes = parseInt(rawNum, 10) || 0;
            }
        }

        // Detect if this is a child comment (Reply) and who it is replying to
        let isReply = false;
        let replyTo = "";
        const allText = el.innerText || "";

        // Check 1: Explicit 'Đang trả lời @...' or 'Replying to @...'
        const replyMatch = allText.match(/(?:đang trả lời|replying to|trả lời)\\s*@?([A-Za-z0-9_.-]+)/i);
        if (replyMatch) {
            isReply = true;
            replyTo = `@${replyMatch[1].replace(/^@/, '')}`;
        }

        // Check 2: Check for tagged user link in reply header
        if (!replyTo) {
            const taggedLinks = el.querySelectorAll('a[href^="/@"]');
            for (const tl of taggedLinks) {
                const tHref = tl.getAttribute('href') || "";
                const m = tHref.match(/@([^/?#]+)/);
                if (m && m[1] !== username) {
                    const prevText = tl.previousSibling ? (tl.previousSibling.textContent || "") : "";
                    if (prevText.toLowerCase().includes("trả lời") || prevText.toLowerCase().includes("replying")) {
                        isReply = true;
                        replyTo = `@${m[1]}`;
                        break;
                    }
                }
            }
        }

        // Check 3: Check visual hierarchy (connector line or indentation)
        if (!isReply) {
            const style = window.getComputedStyle(el);
            const paddingLeft = parseInt(style.paddingLeft || '0', 10);
            const marginLeft = parseInt(style.marginLeft || '0', 10);
            const hasConnectorLine = el.querySelector('div[style*="border-left"], svg[aria-label*="line"]') !== null;
            
            if (paddingLeft > 24 || marginLeft > 16 || hasConnectorLine) {
                isReply = true;
            }
        }

        // Find embedded images
        const imgs = Array.from(el.querySelectorAll('img')).map(i => i.src).filter(src => 
            src && !src.includes('profile') && !src.includes('avatar') && !src.includes('s150x150')
        );
        
        // Find clean text content
        const contentCandidates = el.querySelectorAll('div[dir="auto"], span[dir="auto"]');
        let chosenContent = "";
        let longestLen = 0;

        for (const cand of contentCandidates) {
            let t = (cand.innerText || "").trim();
            // Clean out 'Translate' or 'Dịch'
            t = t.replace(/\\s*(Translate|Dịch)\\s*$/i, '').trim();
            
            // Skip badges, dates, user handles, numbers
            if (t === username || t === authorName || t === 'Author' || t === 'Tác giả' || t === 'Pinned' || t === 'Ghim' || t === 'Edited' || t === 'Đã chỉnh sửa') continue;
            if (/^\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}$/.test(t)) continue;
            if (/^\\d+[smhdwy]$/.test(t)) continue;
            if (/^\\d+(\\.\\d+)?[KMB]?$/i.test(t)) continue;
            if (/^(?:đang trả lời|replying to)\\s*@?[A-Za-z0-9_.-]+$/i.test(t)) continue;
            if (['Like', 'Reply', 'Repost', 'Share', 'Thread', 'Follow', 'Đang theo dõi', 'Theo dõi', 'Thích', 'Trả lời'].includes(t)) continue;

            if (t.length > longestLen) {
                longestLen = t.length;
                chosenContent = t;
            }
        }
        
        // Fallback to concatenating spans if no candidate found
        if (!chosenContent) {
            const textSpans = el.querySelectorAll('span[dir="auto"], div[dir="auto"], span');
            let extractedParts = [];
            textSpans.forEach(s => {
                let t = (s.innerText || "").trim();
                t = t.replace(/\\s*(Translate|Dịch)\\s*$/i, '').trim();
                if (t.length > 1 && 
                    !['Like', 'Reply', 'Repost', 'Share', 'Thread', 'Follow', 'Đang theo dõi', 'Theo dõi', 'Thích', 'Trả lời', 'Author', 'Pinned', 'Ghim', 'Edited'].includes(t) &&
                    !t.match(/^\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}$/) &&
                    !t.match(/^\\d+[smhdwy]$/) && 
                    !t.match(/^\\d+(\\.\\d+)?[KMB]?$/) &&
                    !t.match(/^(?:đang trả lời|replying to)\\s*@?[A-Za-z0-9_.-]+$/i) &&
                    t !== username &&
                    t !== authorName) {
                    extractedParts.push(t);
                }
            });
            chosenContent = [...new Set(extractedParts)].join(" ").trim();
        }

        const lowerContent = chosenContent.toLowerCase();
        const isLoginWallText = (
            lowerContent.includes("say more with threads") ||
            lowerContent.includes("continue with instagram") ||
            lowerContent.includes("tiếp tục bằng instagram") ||
            lowerContent.includes("join threads to share thoughts") ||
            lowerContent.includes("tham gia threads để chia sẻ") ||
            lowerContent.includes("nói nhiều hơn với threads")
        );
        
        if (chosenContent && chosenContent.length >= 2 && !isLoginWallText && !seenTexts.has(chosenContent)) {
            seenTexts.add(chosenContent);
            results.push({
                index: index,
                username: username,
                authorName: authorName,
                authorProfileUrl: authorProfileUrl,
                itemUrl: itemUrl,
                timeStr: timeStr,
                likes: likes,
                isReply: isReply,
                replyTo: replyTo,
                imageUrls: imgs.slice(0, 3),
                content: chosenContent
            });
        }
    });
    
    return results;
})();
"""

def generate_item_id(prefix: str, url: str, content: str, username: str) -> str:
    """Generate a deterministic unique ID for a post or comment."""
    if url and "/post/" in url:
        match = re.search(r'/post/([A-Za-z0-9_-]+)', url)
        if match:
            return f"{prefix}_{match.group(1)}"
    hash_val = hashlib.md5(f"{username}_{content}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{hash_val}"
