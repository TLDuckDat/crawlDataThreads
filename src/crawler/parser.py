import re
import hashlib
from typing import List, Dict, Any, Optional

EXPAND_MORE_BUTTONS_JS = """
return (() => {
    let clicked = 0;
    const candidates = document.querySelectorAll('div[role="button"], span, button, a[role="button"]');
    for (const el of candidates) {
        // Do not click buttons inside login or modal dialogs
        if (el.closest('div[role="dialog"], [aria-modal="true"]')) {
            continue;
        }
        const text = (el.innerText || "").trim().toLowerCase();
        const aria = (el.getAttribute('aria-label') || "").toLowerCase();
        
        const isExpand = (
            text === "xem thêm" || 
            text === "more" || 
            text === "view more" ||
            text.includes("xem thêm câu trả lời") ||
            text.includes("xem câu trả lời") ||
            text.includes("câu trả lời khác") ||
            text.includes("xem thêm phản hồi") ||
            text.includes("xem phản hồi") ||
            text.includes("phản hồi khác") ||
            text.includes("view replies") ||
            text.includes("view reply") ||
            text.includes("view more replies") ||
            text.includes("more replies") ||
            /\\d+\\s*(câu trả lời|phản hồi|replies|reply)/i.test(text) ||
            aria.includes("view replies") ||
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
    // 1. Scroll container in Threads is typically #scrollview
    const scrollContainer = document.getElementById('scrollview') || 
                           document.querySelector('div[id="scrollview"]') ||
                           document.querySelector('div[style*="overflow-y"]') ||
                           document.documentElement;

    // 2. Scroll the last rendered item into view to trigger Virtual DOM loading
    const items = document.querySelectorAll('div[data-pressable-container="true"], div[role="article"]');
    if (items.length > 0) {
        items[items.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
    }

    // 3. Scroll container and window
    if (scrollContainer && scrollContainer !== document.documentElement) {
        scrollContainer.scrollTop += 1400;
    }
    window.scrollBy(0, 1400);

    return {
        itemsCount: items.length,
        containerScrollTop: scrollContainer ? scrollContainer.scrollTop : 0
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
    
    // Find all article or container cards in Threads feed/post page
    const elements = document.querySelectorAll('div[data-pressable-container="true"], div[role="article"], div[tabindex="-1"]');
    
    elements.forEach((el, index) => {
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
        const allText = el.innerText || "";
        const likeMatch = allText.match(/(\\d+[\\d,.]*)\\s*(lượt thích|thích|likes?)/i);
        if (likeMatch) {
            const rawNum = likeMatch[1].replace(/[,.]/g, '');
            likes = parseInt(rawNum, 10) || 0;
        }

        // Detect if this is a child comment (Reply) and who it is replying to
        let isReply = false;
        let replyTo = "";

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
        
        // Find text content
        const textSpans = el.querySelectorAll('span[dir="auto"], div[dir="auto"], span');
        let extractedParts = [];
        textSpans.forEach(s => {
            const t = (s.innerText || "").trim();
            if (t.length > 1 && 
                !['Like', 'Reply', 'Repost', 'Share', 'Thread', 'Follow', 'Đang theo dõi', 'Theo dõi', 'Thích', 'Trả lời'].includes(t) &&
                !t.match(/^\\d+[smhdwy]$/) && 
                !t.match(/^\\d+(\\.\\d+)?[KMB]?$/) &&
                !t.match(/^(?:đang trả lời|replying to)\\s*@?[A-Za-z0-9_.-]+$/i) &&
                t !== username &&
                t !== authorName) {
                extractedParts.push(t);
            }
        });
        
        // Deduplicate overlapping texts from nested spans
        const fullContent = [...new Set(extractedParts)].join(" ").trim();
        const lowerContent = fullContent.toLowerCase();

        // Filter out login wall strings or empty prompts
        const isLoginWallText = (
            lowerContent.includes("say more with threads") ||
            lowerContent.includes("continue with instagram") ||
            lowerContent.includes("tiếp tục bằng instagram") ||
            lowerContent.includes("join threads to share thoughts") ||
            lowerContent.includes("tham gia threads để chia sẻ") ||
            lowerContent.includes("nói nhiều hơn với threads")
        );
        
        if (fullContent && fullContent.length >= 2 && !isLoginWallText && !seenTexts.has(fullContent)) {
            seenTexts.add(fullContent);
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
                content: fullContent
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
