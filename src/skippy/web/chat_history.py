import logging
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from skippy.db_utils import get_db_connection
from .shared_ui import render_html_page, render_page_header, render_section

logger = logging.getLogger("skippy")

router = APIRouter()


def _source_from_thread(thread_id: str) -> str:
    if thread_id.startswith("telegram-"):
        return "Telegram"
    if thread_id.startswith("owui-"):
        return "Web"
    if thread_id.startswith("voice-"):
        return "Voice"
    if thread_id.startswith("scheduled-"):
        return "Scheduled"
    return "Other"


@router.get("/api/chat-history")
async def get_chat_history(
    limit: int = Query(default=20, ge=1, le=100),
    source: str = Query(default="all"),
):
    """Return recent individual chat messages across all threads."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langchain_core.messages import HumanMessage, AIMessage

    serde = JsonPlusSerializer()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Fetch more than needed to account for filtering by source
                fetch_limit = limit * 4 if source != "all" else limit * 2
                fetch_limit = max(fetch_limit, 200)

                await cur.execute(
                    """
                    SELECT
                        cw.thread_id,
                        cw.blob,
                        cw.type,
                        c.checkpoint->>'ts' AS ts
                    FROM checkpoint_writes cw
                    JOIN checkpoints c
                        ON cw.thread_id = c.thread_id
                        AND cw.checkpoint_ns = c.checkpoint_ns
                        AND cw.checkpoint_id = c.checkpoint_id
                    WHERE cw.channel = 'messages'
                        AND cw.thread_id NOT LIKE 'scheduled-%%'
                    ORDER BY c.checkpoint->>'ts' DESC
                    LIMIT %s
                    """,
                    (fetch_limit,),
                )
                rows = await cur.fetchall()

        messages: list[dict[str, Any]] = []

        for thread_id, blob, typ, ts in rows:
            src = _source_from_thread(thread_id)

            if source != "all" and src.lower() != source.lower():
                continue

            try:
                obj = serde.loads_typed((typ, bytes(blob)))
            except Exception:
                logger.debug("Failed to decode blob for thread %s", thread_id)
                continue

            # Each write blob may be a single message or a list of messages
            items = obj if isinstance(obj, list) else [obj]
            for msg in items:
                if isinstance(msg, HumanMessage):
                    role = "user"
                elif isinstance(msg, AIMessage):
                    role = "assistant"
                else:
                    continue  # skip SystemMessage, ToolMessage, etc.

                content = msg.content
                if isinstance(content, list):
                    # Handle multi-part content (tool use blocks, etc.)
                    parts = [
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in content
                        if not (isinstance(p, dict) and p.get("type") == "tool_use")
                    ]
                    content = " ".join(p for p in parts if p).strip()

                if not content:
                    continue

                messages.append(
                    {
                        "role": role,
                        "content": str(content),
                        "timestamp": ts,
                        "source": src,
                        "thread_id": thread_id,
                    }
                )

            if len(messages) >= limit:
                break

        return messages[:limit]

    except Exception:
        logger.exception("Failed to fetch chat history")
        return []


@router.get("/chat-history", response_class=HTMLResponse)
async def chat_history_page():
    return CHAT_HISTORY_PAGE_HTML


def get_chat_history_page_html() -> str:
    page_content = render_page_header(
        "💬 Chat History",
        "Recent messages across all conversations",
    )

    nav_html = '''
        <div class="page-controls">
            <a href="/" class="btn btn-ghost">← Back to Dashboard</a>
        </div>'''

    controls_html = '''
        <div class="page-controls">
            <select id="limitSelect">
                <option value="20" selected>Last 20 messages</option>
                <option value="50">Last 50 messages</option>
                <option value="100">Last 100 messages</option>
            </select>
            <select id="sourceSelect">
                <option value="all" selected>All Sources</option>
                <option value="telegram">Telegram</option>
                <option value="web">Web</option>
                <option value="voice">Voice</option>
            </select>
            <button class="btn btn-ghost" onclick="loadMessages()" style="margin-left:auto;">↻ Refresh</button>
            <span class="text-muted" id="msgCount"></span>
        </div>'''

    chat_html = '''
        <div id="chatContainer" class="chat-container">
            <div class="text-center text-muted" style="padding: 2rem;">Loading messages...</div>
        </div>'''

    section_html = render_section("Messages", controls_html + chat_html)

    page_content += nav_html
    page_content += section_html

    scripts = '''
    <style>
        .chat-container {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            padding: 0.5rem 0;
        }

        .msg-row {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
            max-width: 80%;
        }

        .msg-row.user { align-self: flex-end; align-items: flex-end; }
        .msg-row.assistant { align-self: flex-start; align-items: flex-start; }

        .msg-bubble {
            padding: 0.65rem 1rem;
            border-radius: 16px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            font-size: 0.9rem;
        }

        .msg-row.user .msg-bubble {
            background: rgba(99, 102, 241, 0.25);
            border: 1px solid rgba(99, 102, 241, 0.4);
            border-bottom-right-radius: 4px;
        }

        .msg-row.assistant .msg-bubble {
            background: var(--bg-card, rgba(255,255,255,0.05));
            border: 1px solid var(--border, rgba(255,255,255,0.1));
            border-bottom-left-radius: 4px;
        }

        .msg-meta {
            font-size: 0.72rem;
            color: var(--text-faint, #666);
            display: flex;
            gap: 0.4rem;
            align-items: center;
        }

        .source-badge {
            font-size: 0.65rem;
            padding: 1px 6px;
            border-radius: 10px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .source-Telegram { background: rgba(41, 182, 246, 0.15); color: #29b6f6; }
        .source-Web { background: rgba(102, 187, 106, 0.15); color: #66bb6a; }
        .source-Voice { background: rgba(255, 167, 38, 0.15); color: #ffa726; }
        .source-Other { background: rgba(158, 158, 158, 0.15); color: #9e9e9e; }

        .msg-label {
            font-size: 0.72rem;
            font-weight: 600;
            color: var(--text-muted, #aaa);
        }

        @media (max-width: 768px) {
            .msg-row { max-width: 95%; }
        }
    </style>

    <script>
        const limitEl = document.getElementById('limitSelect');
        const sourceEl = document.getElementById('sourceSelect');
        const container = document.getElementById('chatContainer');
        const msgCount = document.getElementById('msgCount');

        function esc(s) {
            const d = document.createElement('div');
            d.textContent = s ?? '';
            return d.innerHTML;
        }

        function fmtTime(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            const now = new Date();
            const diffMs = now - d;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            let relative;
            if (diffMins < 1) relative = 'just now';
            else if (diffMins < 60) relative = diffMins + 'm ago';
            else if (diffHours < 24) relative = diffHours + 'h ago';
            else if (diffDays < 7) relative = diffDays + 'd ago';
            else relative = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

            const absolute = d.toLocaleString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric',
                hour: 'numeric', minute: '2-digit'
            });
            return `<span title="${esc(absolute)}">${esc(relative)}</span>`;
        }

        async function loadMessages() {
            container.innerHTML = '<div class="text-center text-muted" style="padding:2rem;">Loading...</div>';
            const limit = limitEl.value;
            const source = sourceEl.value;
            try {
                const res = await fetch('/api/chat-history?limit=' + limit + '&source=' + source);
                const data = await res.json();
                msgCount.textContent = data.length + ' message' + (data.length === 1 ? '' : 's');

                if (!data.length) {
                    container.innerHTML = '<div class="text-center text-muted" style="padding:2rem;">No messages found.</div>';
                    return;
                }

                // API returns newest-first; reverse so oldest is at top
                const msgs = [...data].reverse();

                container.innerHTML = msgs.map(m => {
                    const isUser = m.role === 'user';
                    const label = isUser ? 'You' : 'Skippy';
                    return `
                        <div class="msg-row ${esc(m.role)}">
                            <div class="msg-meta">
                                <span class="msg-label">${esc(label)}</span>
                                <span class="source-badge source-${esc(m.source)}">${esc(m.source)}</span>
                                ${fmtTime(m.timestamp)}
                            </div>
                            <div class="msg-bubble">${esc(m.content)}</div>
                        </div>
                    `;
                }).join('');

                // Scroll to bottom to show most recent
                container.scrollTop = container.scrollHeight;

            } catch (err) {
                container.innerHTML = '<div class="text-center text-muted" style="padding:2rem;">Failed to load messages.</div>';
            }
        }

        limitEl.addEventListener('change', loadMessages);
        sourceEl.addEventListener('change', loadMessages);

        loadMessages();
    </script>
    '''

    return render_html_page("Chat History", page_content, extra_scripts=scripts)


CHAT_HISTORY_PAGE_HTML = get_chat_history_page_html()
