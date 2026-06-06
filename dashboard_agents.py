import asyncio
import csv
import datetime
import re

import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Portfolio Agent Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .stApp { background: #f1f5f9; }
    .block-container { padding-top: 1.5rem; max-width: 1100px; }
    section[data-testid="stSidebar"] { display: none; }
    /* Global dark navy for all Streamlit-rendered text */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    .stMarkdown p, .stMarkdown li, .stMarkdown span, .stMarkdown a,
    [data-testid="stMarkdownContainer"] *,
    [data-testid="stText"], [data-testid="caption"],
    .stChatMessage p, .stChatMessage span,
    label, .stMetric label, .stMetric [data-testid="stMetricValue"],
    .stMetric [data-testid="stMetricDelta"] { color: #0d1b35 !important; }
    .office-label {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: #0d1b35;
        margin-bottom: 10px;
    }
    div[data-testid="stChatInput"] > div { border-radius: 14px; }
</style>
""", unsafe_allow_html=True)

# ── session state ────────────────────────────────────────────────────────────

def _init():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_states" not in st.session_state:
        st.session_state.agent_states = {
            "main":      {"status": "idle", "last_action": "Waiting for your command..."},
            "news":      {"status": "idle", "last_action": "Standing by"},
            "price":     {"status": "idle", "last_action": "Standing by"},
            "portfolio": {"status": "idle", "last_action": "Standing by"},
            "sage":      {"status": "idle", "last_action": "Standing by"},
            "vyse":      {"status": "idle", "last_action": "Standing by"},
        }
    if "last_result" not in st.session_state:
        st.session_state.last_result = None

_init()

# ── portfolio ────────────────────────────────────────────────────────────────

def read_portfolio():
    try:
        with open("portfolio.csv", newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []

PORTFOLIO = read_portfolio()
TICKERS   = [s["ticker"] for s in PORTFOLIO]

# ── agent metadata ───────────────────────────────────────────────────────────

AGENTS = {
    "main":      {"icon": "🧠", "label": "Main Agent",      "desc": "Commander & Router"},
    "news":      {"icon": "📰", "label": "Tracker",          "desc": "Yahoo Finance Headlines"},
    "price":     {"icon": "💹", "label": "Clove",             "desc": "Live Stock Prices"},
    "portfolio": {"icon": "📁", "label": "Portfolio Agent",  "desc": "Manages portfolio.csv"},
    "sage":      {"icon": "🔮", "label": "Sage",             "desc": "News Summariser"},
    "vyse":      {"icon": "🎯", "label": "Vyse",             "desc": "Entry Point Calculator"},
}

# ── agent card HTML ──────────────────────────────────────────────────────────

def agent_card(agent_id: str) -> str:
    state  = st.session_state.agent_states[agent_id]
    meta   = AGENTS[agent_id]
    active = state["status"] == "active"

    if active:
        bg, border = "#f0fdf4", "2px solid #22c55e"
        glow        = "box-shadow:0 0 18px rgba(34,197,94,.28);"
        dot, dlabel = "#22c55e", "● Active"
        dlabel_col  = "#16a34a"
    else:
        bg, border = "#ffffff", "1.5px solid #e2e8f0"
        glow        = ""
        dot, dlabel = "#cbd5e1", "○ Idle"
        dlabel_col  = "#0d1b35"

    last = state["last_action"]
    last_short = (last[:54] + "…") if len(last) > 56 else last

    return f"""
    <div style="background:{bg};border:{border};border-radius:14px;padding:18px 16px;
                {glow}min-height:150px;display:flex;flex-direction:column;gap:5px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:1.75rem;line-height:1">{meta['icon']}</span>
            <span style="font-size:.72rem;font-weight:700;color:{dlabel_col}">{dlabel}</span>
        </div>
        <div style="font-weight:800;font-size:.95rem;color:#0d1b35">{meta['label']}</div>
        <div style="font-size:.72rem;color:#0d1b35">{meta['desc']}</div>
        <div style="margin-top:auto;background:#f1f5f9;border-radius:7px;padding:7px 10px;
                    font-size:.75rem;color:#0d1b35;line-height:1.45" title="{last}">
            {last_short}
        </div>
    </div>"""

# ── routing ──────────────────────────────────────────────────────────────────

def route(query: str) -> str:
    q = query.lower()

    # ── Ticker detection → full Sage briefing ─────────────────────────────────
    # 1. $TICKER or $ticker (most explicit — always Sage)
    if re.search(r'\$[A-Za-z]{2,5}\b', query):
        return "sage"

    # 2. Portfolio tickers mentioned in any case ("nvda", "NVDA", "Nvda")
    for ticker in TICKERS:
        if re.search(rf'\b{re.escape(ticker)}\b', query, re.IGNORECASE):
            return "sage"

    # 3. Company names typed in plain English ("nvidia", "apple", "servicenow")
    for name in COMPANY_MAP:
        if name in q:
            return "sage"

    # 4. Known ticker symbols from company map typed directly ("NOW", "AAPL")
    known_symbols = set(COMPANY_MAP.values())
    for word in re.findall(r'\b[A-Za-z]{2,5}\b', query):
        if word.upper() in known_symbols and word.upper() not in STOPWORDS:
            return "sage"

    # ── Keyword routing ───────────────────────────────────────────────────────
    if any(w in q for w in ["news", "headline", "article", "latest", "happening", "story", "report",
                             "summarize", "summary", "sage", "overview", "brief", "digest",
                             "describe", "overall", "today"]):
        return "sage"
    if any(w in q for w in ["price", "worth", "how much", "trading at", "current price", "live"]):
        return "price"
    if any(w in q for w in ["portfolio", "holding", "allocation", "position", "total", "my stock", "show me my"]):
        return "portfolio"
    return "portfolio"

# ── ticker extraction ────────────────────────────────────────────────────────

def extract_tickers(query: str) -> list[str]:
    found = []
    for w in re.findall(r'\b[A-Z]{2,5}\b', query):
        if w in TICKERS and w not in found:
            found.append(w)
    if not found:
        for t in TICKERS:
            if t.lower() in query.lower() and t not in found:
                found.append(t)
    return found or TICKERS

# ── agent runners ─────────────────────────────────────────────────────────────

COMPANY_MAP = {
    "apple": "AAPL", "microsoft": "MSFT", "amazon": "AMZN", "google": "GOOGL",
    "alphabet": "GOOGL", "meta": "META", "facebook": "META", "netflix": "NFLX",
    "tesla": "TSLA", "nvidia": "NVDA", "amd": "AMD", "intel": "INTC",
    "palantir": "PLTR", "shopify": "SHOP", "coinbase": "COIN", "robinhood": "HOOD",
    "spotify": "SPOT", "uber": "UBER", "airbnb": "ABNB", "snowflake": "SNOW",
    "arm": "ARM", "broadcom": "AVGO", "intuitive": "ISRG", "servicenow": "NOW",
    "iridium": "IREN",
}

STOPWORDS = {"I", "A", "AN", "THE", "AND", "OR", "FOR", "AT", "IN", "ON",
             "OF", "TO", "IS", "ARE", "MY", "ME", "IT", "BE", "DO", "US"}

def extract_tickers_news(query: str) -> list[str]:
    found = []
    q_lower = query.lower()

    # 1. Uppercase ticker symbols typed directly (e.g. AAPL, MSFT)
    for w in re.findall(r'\b[A-Z]{2,5}\b', query):
        if w not in STOPWORDS and w not in found:
            found.append(w)

    # 2. Company names typed in plain English (e.g. "apple", "tesla")
    for name, ticker in COMPANY_MAP.items():
        if name in q_lower and ticker not in found:
            found.append(ticker)

    # 3. Portfolio tickers mentioned in lowercase (e.g. "nvda")
    if not found:
        for t in TICKERS:
            if t.lower() in q_lower and t not in found:
                found.append(t)

    # 4. Last resort — fall back to full portfolio
    return (found or TICKERS)[:3]

TODAY_KEYWORDS = ["today", "recent", "latest today", "check news today", "this morning", "right now", "now"]

def _parse_news_item(raw: dict) -> dict | None:
    """Normalize yfinance news item (new nested format) into a flat dict."""
    content = raw.get("content", {})
    if not content:
        return None
    title = content.get("title", "")
    if not title:
        return None
    link = (content.get("clickThroughUrl") or content.get("canonicalUrl") or {}).get("url", "#")
    publisher = (content.get("provider") or {}).get("displayName", "")
    pub_date_str = content.get("pubDate") or content.get("displayTime") or ""
    ts = None
    if pub_date_str:
        try:
            dt = datetime.datetime.strptime(pub_date_str[:19], "%Y-%m-%dT%H:%M:%S")
            ts = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            pass
    summary = content.get("summary", "")
    return {"title": title, "link": link, "publisher": publisher,
            "providerPublishTime": ts, "summary": summary}

def run_news(query: str):
    q_lower = query.lower()
    filter_today = any(w in q_lower for w in TODAY_KEYWORDS)
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=15)).timestamp() if filter_today else None

    results = []
    for ticker in extract_tickers_news(query):
        try:
            raw_news = yf.Ticker(ticker).news or []
            normalized = [n for raw in raw_news if (n := _parse_news_item(raw))]
            if cutoff:
                filtered = [n for n in normalized if (n["providerPublishTime"] or 0) >= cutoff]
            else:
                filtered = normalized[:4]
            results.append({"ticker": ticker, "news": filtered, "today_filter": filter_today})
        except Exception as e:
            results.append({"ticker": ticker, "news": [], "error": str(e), "today_filter": filter_today})
    return results


def run_price(query: str):
    results = []
    for ticker in extract_tickers(query):
        try:
            t     = yf.Ticker(ticker)
            info  = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev  = info.get("previousClose")
            chg   = ((price - prev) / prev * 100) if price and prev else None

            # 20-day MA from recent history (50-day MA comes directly from info)
            hist = t.history(period="3mo")
            ma20 = round(float(hist["Close"].tail(20).mean()), 2) if len(hist) >= 20 else None

            results.append({
                "ticker":      ticker,
                "price":       price,
                "change_pct":  chg,
                "week52_high": info.get("fiftyTwoWeekHigh"),
                "week52_low":  info.get("fiftyTwoWeekLow"),
                "volume":      info.get("volume") or info.get("regularMarketVolume"),
                "ma20":        ma20,
                "ma50":        info.get("fiftyDayAverage"),
                "market_cap":  info.get("marketCap"),
                "pe_ratio":    info.get("trailingPE"),
            })
        except Exception as e:
            results.append({"ticker": ticker, "price": None, "change_pct": None, "error": str(e)})
    return results


def run_portfolio(_query: str):
    return read_portfolio()

# ── result renderers ─────────────────────────────────────────────────────────

def render_news(data):
    for item in data:
        label = "Last 15 Hours" if item.get("today_filter") else "Latest Headlines"
        st.markdown(f"#### 📰 {item['ticker']} — {label}")
        if item.get("error"):
            st.error(item["error"]); continue
        if not item["news"]:
            msg = "No news in the last 15 hours." if item.get("today_filter") else "No recent news found."
            st.info(msg); continue
        for n in item["news"]:
            ts       = n.get("providerPublishTime")
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%b %d, %Y %H:%M") if ts else ""
            st.markdown(f"""
            <a href="{n.get('link','#')}" target="_blank" style="text-decoration:none;color:inherit">
            <div style="background:#f8fafc;border-left:3px solid #3b82f6;
                        border-radius:0 8px 8px 0;padding:12px 14px;margin-bottom:8px">
                <div style="font-weight:600;font-size:.875rem;color:#0d1b35;line-height:1.45">{n.get('title','')}</div>
                <div style="font-size:.72rem;color:#0d1b35;margin-top:4px">{n.get('publisher','')} · {time_str}</div>
            </div></a>""", unsafe_allow_html=True)


def _fmt_vol(v):
    if not isinstance(v, (int, float)): return "N/A"
    if v >= 1_000_000_000: return f"{v/1_000_000_000:.1f}B"
    if v >= 1_000_000:     return f"{v/1_000_000:.1f}M"
    if v >= 1_000:         return f"{v/1_000:.1f}K"
    return str(int(v))

def _fmt_cap(v):
    if not isinstance(v, (int, float)): return "N/A"
    if v >= 1_000_000_000_000: return f"${v/1_000_000_000_000:.2f}T"
    if v >= 1_000_000_000:     return f"${v/1_000_000_000:.2f}B"
    return f"${v/1_000_000:.1f}M"

def _fmt_ma(v):
    return f"${v:.2f}" if isinstance(v, (int, float)) else "N/A"

def _fmt_pe(v):
    return f"{v:.1f}x" if isinstance(v, (int, float)) else "N/A"


def render_price(data):
    cols = st.columns(min(len(data), 3))
    for i, item in enumerate(data):
        with cols[i % len(cols)]:
            price = item.get("price")
            chg   = item.get("change_pct")
            price_str = f"${price:.2f}" if isinstance(price, (int, float)) else "N/A"
            if chg is not None:
                chg_str, chg_col = f"{chg:+.2f}%", ("#16a34a" if chg >= 0 else "#dc2626")
            else:
                chg_str, chg_col = "N/A", "#94a3b8"
            h52, l52 = item.get("week52_high"), item.get("week52_low")
            range_str = (f"${l52:.2f} – ${h52:.2f}"
                         if isinstance(h52, float) and isinstance(l52, float) else "N/A")

            vol_str = _fmt_vol(item.get("volume"))
            cap_str = _fmt_cap(item.get("market_cap"))
            ma20_str = _fmt_ma(item.get("ma20"))
            ma50_str = _fmt_ma(item.get("ma50"))
            pe_str  = _fmt_pe(item.get("pe_ratio"))

            st.markdown(f"""
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;
                        padding:20px 16px;margin-bottom:8px">

                <!-- Price header -->
                <div style="text-align:center;padding-bottom:14px;
                            border-bottom:1px solid #f1f5f9;margin-bottom:14px">
                    <div style="font-size:1.1rem;font-weight:800;color:#0d1b35">{item['ticker']}</div>
                    <div style="font-size:1.8rem;font-weight:700;margin:6px 0;color:#0d1b35">{price_str}</div>
                    <div style="font-size:.9rem;font-weight:700;color:{chg_col}">{chg_str} วันนี้</div>
                    <div style="font-size:.7rem;color:#94a3b8;margin-top:6px">52 สัปดาห์: {range_str}</div>
                </div>

                <!-- Metrics grid -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:7px">
                    <div style="background:#f8fafc;border-radius:8px;padding:9px 11px">
                        <div style="font-size:.65rem;font-weight:700;color:#64748b;
                                    letter-spacing:.04em;margin-bottom:3px">ปริมาณซื้อขาย</div>
                        <div style="font-size:.9rem;font-weight:700;color:#0d1b35">{vol_str}</div>
                    </div>
                    <div style="background:#f8fafc;border-radius:8px;padding:9px 11px">
                        <div style="font-size:.65rem;font-weight:700;color:#64748b;
                                    letter-spacing:.04em;margin-bottom:3px">มูลค่าตลาด</div>
                        <div style="font-size:.9rem;font-weight:700;color:#0d1b35">{cap_str}</div>
                    </div>
                    <div style="background:#f8fafc;border-radius:8px;padding:9px 11px">
                        <div style="font-size:.65rem;font-weight:700;color:#64748b;
                                    letter-spacing:.04em;margin-bottom:3px">MA 20 วัน</div>
                        <div style="font-size:.9rem;font-weight:700;color:#0d1b35">{ma20_str}</div>
                    </div>
                    <div style="background:#f8fafc;border-radius:8px;padding:9px 11px">
                        <div style="font-size:.65rem;font-weight:700;color:#64748b;
                                    letter-spacing:.04em;margin-bottom:3px">MA 50 วัน</div>
                        <div style="font-size:.9rem;font-weight:700;color:#0d1b35">{ma50_str}</div>
                    </div>
                    <div style="background:#f8fafc;border-radius:8px;padding:9px 11px;
                                grid-column:1/-1">
                        <div style="font-size:.65rem;font-weight:700;color:#64748b;
                                    letter-spacing:.04em;margin-bottom:3px">อัตราส่วน P/E</div>
                        <div style="font-size:.9rem;font-weight:700;color:#0d1b35">{pe_str}</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)


def render_portfolio(data):
    total = sum(float(s["value_usd"]) for s in data)
    st.markdown(f"**Total Portfolio Value: ${total:,.2f}**")
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    for s in data:
        chg       = float(s["change_today"])
        chg_col   = "#16a34a" if chg >= 0 else "#dc2626"
        is_lt     = s["type"] == "long_term"
        badge_bg  = "#eff6ff" if is_lt else "#fff7ed"
        badge_col = "#1d4ed8" if is_lt else "#c2410c"
        badge_txt = "Long Term" if is_lt else "Trading"
        st.markdown(f"""
        <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:10px;
                    padding:12px 16px;margin-bottom:7px;
                    display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-weight:800;font-size:1.05rem;color:#0d1b35">{s['ticker']}</span>
                <span style="font-size:.68rem;font-weight:600;padding:2px 8px;border-radius:10px;
                             background:{badge_bg};color:{badge_col};margin-left:8px">{badge_txt}</span>
            </div>
            <div style="text-align:right">
                <div style="font-weight:700;color:#0d1b35">${float(s['value_usd']):.2f}</div>
                <div style="font-size:.78rem;font-weight:600;color:{chg_col}">{chg:+.2f}% today · {s['weight']}% weight</div>
            </div>
        </div>""", unsafe_allow_html=True)


def _analyze_stock(b: dict) -> dict:
    """Pure-Python analysis of price data + Thai news text. No external API."""
    pd_     = b.get("price") or {}
    articles = b.get("articles", [])

    price   = pd_.get("price")
    ma20    = pd_.get("ma20")
    ma50    = pd_.get("ma50")
    pe      = pd_.get("pe_ratio")
    vol     = pd_.get("volume")
    avg_vol = pd_.get("avg_volume")

    signals = []   # "bullish" | "bearish" | "mixed" | "expensive" | "high_vol" | "pos_news" | "neg_news"
    reasons = []

    # ── Trend: price vs MA20 & MA50 ──────────────────────────────────────────
    trend_label = None
    if all(isinstance(v, (int, float)) for v in (price, ma20, ma50)):
        if price > ma20 and price > ma50:
            trend_label = "แนวโน้มขาขึ้น 📈"
            signals.append("bullish")
            reasons.append(f"ราคา ${price:.2f} อยู่เหนือ MA20 (${ma20:.2f}) และ MA50 (${ma50:.2f})")
        elif price < ma20 and price < ma50:
            trend_label = "แนวโน้มขาลง 📉"
            signals.append("bearish")
            reasons.append(f"ราคา ${price:.2f} ต่ำกว่า MA20 (${ma20:.2f}) และ MA50 (${ma50:.2f})")
        else:
            trend_label = "แนวโน้มผสม ↔️"
            signals.append("mixed")
            reasons.append(f"ราคาอยู่ระหว่าง MA20 (${ma20:.2f}) และ MA50 (${ma50:.2f})")

    # ── Valuation: P/E ratio ──────────────────────────────────────────────────
    pe_label = None
    if isinstance(pe, (int, float)) and pe > 0:
        if pe > 30:
            pe_label = "ราคาค่อนข้างแพง ⚠️"
            signals.append("expensive")
            reasons.append(f"P/E = {pe:.1f}x สูงกว่า 30 — หุ้นอาจ Overvalue")
        else:
            pe_label = f"มูลค่าสมเหตุสมผล ✅  (P/E {pe:.1f}x)"

    # ── Volume vs average ─────────────────────────────────────────────────────
    vol_label = None
    if isinstance(vol, (int, float)) and isinstance(avg_vol, (int, float)) and avg_vol > 0:
        ratio = vol / avg_vol
        if ratio >= 1.2:
            vol_label = f"ปริมาณซื้อขายสูง {ratio:.1f}x 🔥"
            signals.append("high_vol")
            reasons.append(f"ปริมาณวันนี้ {_fmt_vol(vol)} สูงกว่าค่าเฉลี่ย {ratio:.1f} เท่า")
        elif ratio <= 0.6:
            vol_label = "ปริมาณซื้อขายต่ำ 📉"
            reasons.append(f"ปริมาณวันนี้ {_fmt_vol(vol)} ต่ำกว่าค่าเฉลี่ย — ความสนใจน้อย")

    # ── News sentiment: count Thai keywords ───────────────────────────────────
    POS_KW = ["เพิ่ม", "พุ่ง", "ดี", "แนะนำ", "กำไร", "เติบโต", "แข็งแกร่ง", "ขึ้น", "บวก", "ดีขึ้น", "สูง"]
    NEG_KW = ["ลด", "ร่วง", "คดี", "ยอมความ", "ขาดทุน", "ลดลง", "ปัญหา", "เสี่ยง", "ตก", "ลบ", "ต่ำ"]

    all_th = " ".join(
        (a.get("title_th", "") + " " + a.get("summary_th", "")) for a in articles
    )
    pos_count = sum(all_th.count(kw) for kw in POS_KW)
    neg_count = sum(all_th.count(kw) for kw in NEG_KW)

    if pos_count > neg_count:
        sentiment_label = "ข่าวเชิงบวก 🟢"
        signals.append("pos_news")
        reasons.append(f"พบคำเชิงบวกในข่าว {pos_count} ครั้ง vs เชิงลบ {neg_count} ครั้ง")
    elif neg_count > pos_count:
        sentiment_label = "ข่าวเชิงลบ 🔴"
        signals.append("neg_news")
        reasons.append(f"พบคำเชิงลบในข่าว {neg_count} ครั้ง vs เชิงบวก {pos_count} ครั้ง")
    else:
        sentiment_label = "ข่าวเป็นกลาง ⚪"
        reasons.append("ข่าวมีทั้งบวกและลบในสัดส่วนใกล้เคียงกัน")

    # ── Overall signal ────────────────────────────────────────────────────────
    bull = signals.count("bullish") + signals.count("high_vol") + signals.count("pos_news")
    bear = signals.count("bearish") + signals.count("expensive") + signals.count("neg_news")

    if bull > bear:
        overall, overall_type = "น่าสนใจ 🟢", "positive"
    elif bear > bull:
        overall, overall_type = "ระวัง 🔴", "negative"
    else:
        overall, overall_type = "รอดูก่อน 🟡", "neutral"

    return {
        "trend_label":     trend_label,
        "pe_label":        pe_label,
        "vol_label":       vol_label,
        "sentiment_label": sentiment_label,
        "overall":         overall,
        "overall_type":    overall_type,
        "reasons":         reasons,
    }


def _translate_batch(texts: list) -> list:
    """Translate a list of strings to Thai using googletrans (concurrent async)."""
    if not texts:
        return texts
    try:
        from googletrans import Translator

        async def _run(ts):
            t = Translator()
            non_empty = [(i, s) for i, s in enumerate(ts) if s.strip()]
            tasks = [t.translate(s, dest="th") for _, s in non_empty]
            raw = await asyncio.gather(*tasks, return_exceptions=True)
            out = list(ts)
            for (i, _), r in zip(non_empty, raw):
                if not isinstance(r, Exception):
                    out[i] = r.text
            return out

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run(texts))
        loop.close()
        return result
    except Exception:
        return texts


def run_vyse(briefings: list) -> list:
    """Pure-Python entry point calculator. Returns one entry dict per ticker."""
    results = []
    for b in briefings:
        ticker      = b["ticker"]
        pd_         = b.get("price") or {}
        price       = pd_.get("price")
        ma20        = pd_.get("ma20")
        ma50        = pd_.get("ma50")
        week52_high = pd_.get("week52_high")
        week52_low  = pd_.get("week52_low")

        if not all(isinstance(v, (int, float)) for v in (price, ma20, ma50)):
            results.append({"ticker": ticker, "error": "ข้อมูลราคาไม่เพียงพอ"})
            continue

        # Support levels
        s1 = round(ma20, 2)
        s2 = round(ma50, 2)
        s3 = round(week52_low, 2) if isinstance(week52_low, (int, float)) else None

        # Resistance levels
        r1 = round(price * 1.05, 2)
        r2 = round(price * 1.10, 2)
        r3 = round(week52_high, 2) if isinstance(week52_high, (int, float)) else None

        # Entry recommendation based on price vs MAs
        if price < ma50:
            entry       = round(price, 2)
            entry_label = f"โซนซื้อดีมาก ${entry:.2f}"
        elif price < ma20:
            entry       = round(ma20 * 0.98, 2)
            entry_label = f"โซนน่าสนใจตอนนี้ ${entry:.2f}"
        else:
            entry       = round(ma20, 2)
            entry_label = f"รอราคาย่อมาที่ ${entry:.2f}"

        # Stop loss: 5% below entry
        stop_loss = round(entry * 0.95, 2)

        # Risk/Reward: gain to R1 vs 5% loss
        potential_gain = r1 - entry
        potential_loss = entry - stop_loss
        rr = round(potential_gain / potential_loss, 1) if potential_loss > 0 else 0

        results.append({
            "ticker":      ticker,
            "s1": s1, "s2": s2, "s3": s3,
            "r1": r1, "r2": r2, "r3": r3,
            "entry_label": entry_label,
            "stop_loss":   stop_loss,
            "rr":          rr,
        })

    return results


def run_sage(query: str):
    # ── Step 1: Tracker fetches news ─────────────────────────────────────────
    news_data = run_news(query)
    total_articles = sum(len(item["news"]) for item in news_data)
    tickers_covered = [item["ticker"] for item in news_data if item["news"]]

    briefings = []
    for item in news_data:
        if not item["news"]:
            continue
        briefings.append({"ticker": item["ticker"], "articles": item["news"], "price": None})

    # ── Step 2: Price Agent fetches price + metrics per ticker ────────────────
    for b in briefings:
        ticker = b["ticker"]
        try:
            t     = yf.Ticker(ticker)
            info  = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev  = info.get("previousClose")
            chg   = ((price - prev) / prev * 100) if price and prev else None
            hist  = t.history(period="3mo")
            ma20  = round(float(hist["Close"].tail(20).mean()), 2) if len(hist) >= 20 else None
            b["price"] = {
                "price":       price,
                "change_pct":  chg,
                "volume":      info.get("volume") or info.get("regularMarketVolume"),
                "avg_volume":  info.get("averageVolume"),
                "ma20":        ma20,
                "ma50":        info.get("fiftyDayAverage"),
                "market_cap":  info.get("marketCap"),
                "pe_ratio":    info.get("trailingPE"),
                "week52_high": info.get("fiftyTwoWeekHigh"),
                "week52_low":  info.get("fiftyTwoWeekLow"),
            }
        except Exception:
            b["price"] = None

    # ── Step 3: Translate all titles + summaries to Thai in one batch ─────────
    if briefings:
        refs, texts = [], []
        for bi, b in enumerate(briefings):
            for ai, a in enumerate(b["articles"]):
                for field, th_field in (("title", "title_th"), ("summary", "summary_th")):
                    val = a.get(field, "").strip()
                    if val:
                        refs.append((bi, ai, th_field))
                        texts.append(val)
        if texts:
            translated = _translate_batch(texts)
            for (bi, ai, th_field), th_text in zip(refs, translated):
                briefings[bi]["articles"][ai][th_field] = th_text

    # ── Step 4: Python analysis (runs after translation so Thai keywords work) ─
    for b in briefings:
        b["analysis"] = _analyze_stock(b)

    # ── Step 5: Vyse calculates entry points from price data ──────────────────
    vyse_data = run_vyse(briefings)

    return {
        "briefings":      briefings,
        "total_articles": total_articles,
        "tickers_covered": tickers_covered,
        "today_filter":   news_data[0].get("today_filter", False) if news_data else False,
        "vyse":           vyse_data,
    }


def render_sage(data):
    briefings      = data["briefings"]
    total_articles = data["total_articles"]
    tickers        = data["tickers_covered"]
    today          = data["today_filter"]
    time_label     = "15 ชั่วโมงล่าสุด" if today else "ล่าสุด"

    if not briefings:
        st.info("Sage ไม่พบข่าวที่จะสรุป")
        return

    # ── Header ────────────────────────────────────────────────────────────────
    now_str = datetime.datetime.now().strftime("%d %b %Y · %H:%M")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border-radius:14px;
                padding:20px 24px;margin-bottom:20px;color:#fff">
        <div style="font-size:.75rem;font-weight:700;letter-spacing:.1em;
                    text-transform:uppercase;opacity:.7;margin-bottom:6px">
            🔮 Sage — สรุปข่าวและราคาหุ้น
        </div>
        <div style="font-size:1.15rem;font-weight:700;margin-bottom:4px">
            {total_articles} บทความ · {len(tickers)} หุ้น — {now_str}
        </div>
        <div style="font-size:.85rem;opacity:.8">
            ครอบคลุม: {' · '.join(tickers)} &nbsp;·&nbsp; ช่วงเวลา: {time_label}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Per-ticker combined card ───────────────────────────────────────────────
    for b in briefings:
        ticker   = b["ticker"]
        articles = b["articles"]
        pd       = b.get("price") or {}

        # ── Price section ─────────────────────────────────────────────────────
        price    = pd.get("price")
        chg      = pd.get("change_pct")
        price_str = f"${price:.2f}" if isinstance(price, (int, float)) else "N/A"
        if chg is not None:
            chg_str = f"{chg:+.2f}% วันนี้"
            chg_col = "#16a34a" if chg >= 0 else "#dc2626"
        else:
            chg_str, chg_col = "N/A", "#94a3b8"

        vol_str = _fmt_vol(pd.get("volume"))
        cap_str = _fmt_cap(pd.get("market_cap"))
        ma20_str = _fmt_ma(pd.get("ma20"))
        ma50_str = _fmt_ma(pd.get("ma50"))
        pe_str  = _fmt_pe(pd.get("pe_ratio"))

        price_html = f"""
        <div style="background:#f5f3ff;border-radius:10px;padding:14px 16px;margin-bottom:12px">
            <div style="display:flex;align-items:baseline;gap:14px;margin-bottom:12px">
                <span style="font-size:1.55rem;font-weight:800;color:#0d1b35">{price_str}</span>
                <span style="font-size:.95rem;font-weight:700;color:{chg_col}">{chg_str}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px">
                <div>
                    <div style="font-size:.6rem;font-weight:700;color:#7c3aed;margin-bottom:2px">ปริมาณ</div>
                    <div style="font-size:.82rem;font-weight:700;color:#0d1b35">{vol_str}</div>
                </div>
                <div>
                    <div style="font-size:.6rem;font-weight:700;color:#7c3aed;margin-bottom:2px">มูลค่าตลาด</div>
                    <div style="font-size:.82rem;font-weight:700;color:#0d1b35">{cap_str}</div>
                </div>
                <div>
                    <div style="font-size:.6rem;font-weight:700;color:#7c3aed;margin-bottom:2px">MA 20 วัน</div>
                    <div style="font-size:.82rem;font-weight:700;color:#0d1b35">{ma20_str}</div>
                </div>
                <div>
                    <div style="font-size:.6rem;font-weight:700;color:#7c3aed;margin-bottom:2px">MA 50 วัน</div>
                    <div style="font-size:.82rem;font-weight:700;color:#0d1b35">{ma50_str}</div>
                </div>
                <div>
                    <div style="font-size:.6rem;font-weight:700;color:#7c3aed;margin-bottom:2px">P/E</div>
                    <div style="font-size:.82rem;font-weight:700;color:#0d1b35">{pe_str}</div>
                </div>
            </div>
        </div>""" if pd else ""

        # ── Analysis section ──────────────────────────────────────────────────
        an = b.get("analysis") or {}
        chips = []
        CHIP = {
            "trend":     (an.get("trend_label"),     "#dcfce7","#15803d", "#fee2e2","#b91c1c", "#f0fdf4","#166534"),
            "pe":        (an.get("pe_label"),         "#fef9c3","#a16207", None,    None,      None,    None),
            "vol":       (an.get("vol_label"),        "#fff7ed","#c2410c", None,    None,      None,    None),
            "sentiment": (an.get("sentiment_label"),  "#dcfce7","#15803d", "#fee2e2","#b91c1c", "#f1f5f9","#475569"),
        }
        for label, pos_bg, pos_col, neg_bg, neg_col, neu_bg, neu_col in CHIP.values():
            if not label:
                continue
            if any(k in label for k in ["📈","🟢","✅"]):
                bg, col = pos_bg, pos_col
            elif any(k in label for k in ["📉","🔴","⚠️"]):
                bg, col = (neg_bg or "#fee2e2"), (neg_col or "#b91c1c")
            elif "🔥" in label:
                bg, col = "#fff7ed", "#c2410c"
            else:
                bg, col = (neu_bg or "#f1f5f9"), (neu_col or "#475569")
            chips.append(
                f'<span style="background:{bg};color:{col};padding:4px 12px;'
                f'border-radius:20px;font-size:.8rem;font-weight:700;white-space:nowrap">{label}</span>'
            )

        overall     = an.get("overall", "")
        overall_type = an.get("overall_type", "neutral")
        ov_bg  = {"positive":"#dcfce7","negative":"#fee2e2","neutral":"#fef9c3"}.get(overall_type,"#f1f5f9")
        ov_col = {"positive":"#15803d","negative":"#b91c1c","neutral":"#a16207"}.get(overall_type,"#475569")

        reasons_html = "".join(
            f'<div style="display:flex;gap:8px;padding:4px 0;align-items:flex-start">'
            f'<span style="color:#7c3aed;flex-shrink:0;font-size:.8rem">•</span>'
            f'<span style="font-size:.8rem;color:#475569;line-height:1.5">{r}</span>'
            f'</div>'
            for r in an.get("reasons", [])
        )

        analysis_html = f"""
        <div style="border:1.5px solid #e9d5ff;border-radius:10px;
                    padding:12px 14px;margin-bottom:12px">
            <div style="font-size:.65rem;font-weight:700;color:#7c3aed;letter-spacing:.07em;
                        text-transform:uppercase;margin-bottom:10px">🔍 การวิเคราะห์</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">
                {''.join(chips)}
            </div>
            <div style="background:{ov_bg};border-radius:8px;padding:10px 14px;margin-bottom:10px;
                        display:flex;align-items:center;justify-content:space-between">
                <div>
                    <div style="font-size:.62rem;font-weight:700;color:#64748b;margin-bottom:3px">
                        สัญญาณโดยรวม
                    </div>
                    <div style="font-size:1.05rem;font-weight:800;color:{ov_col}">{overall}</div>
                </div>
            </div>
            {reasons_html}
        </div>""" if an else ""

        # ── News bullets ──────────────────────────────────────────────────────
        bullets = []
        for a in articles:
            text = (a.get("summary_th") or a.get("summary", "")).strip()
            if not text:
                text = (a.get("title_th") or a.get("title", "")).strip()
            if text:
                bullets.append(text)

        bullet_html = "".join(
            f'<div style="display:flex;gap:10px;padding:8px 0;'
            f'border-bottom:1px solid #f3f0ff;align-items:flex-start">'
            f'<span style="color:#7c3aed;font-size:.9rem;margin-top:2px;flex-shrink:0">▸</span>'
            f'<span style="font-size:.875rem;color:#0d1b35;line-height:1.6">{p}</span>'
            f'</div>'
            for p in bullets
        )

        st.markdown(f"""
        <div style="background:#fff;border:1.5px solid #ede9fe;border-radius:14px;
                    padding:18px 20px;margin-bottom:6px">
            <div style="display:flex;justify-content:space-between;align-items:center;
                        margin-bottom:12px">
                <div style="font-weight:800;font-size:1.15rem;color:#0d1b35">{ticker}</div>
                <div style="font-size:.7rem;font-weight:700;color:#7c3aed;
                            background:#f5f3ff;padding:3px 12px;border-radius:20px">
                    {len(articles)} บทความ
                </div>
            </div>
            {price_html}
            {analysis_html}
            <div style="font-size:.68rem;font-weight:700;color:#7c3aed;letter-spacing:.07em;
                        text-transform:uppercase;margin-bottom:6px">📰 ข่าวล่าสุด</div>
            {bullet_html}
        </div>
        """, unsafe_allow_html=True)

        # Collapsible original articles with links
        with st.expander(f"ดูข่าวต้นฉบับ — {ticker}"):
            for a in articles:
                ts       = a.get("providerPublishTime")
                time_str = datetime.datetime.fromtimestamp(ts).strftime("%d %b · %H:%M") if ts else ""
                st.markdown(f"""
                <a href="{a.get('link','#')}" target="_blank" style="text-decoration:none;color:inherit">
                <div style="background:#f8fafc;border-left:3px solid #a78bfa;
                            border-radius:0 8px 8px 0;padding:10px 12px;margin-bottom:7px">
                    <div style="font-size:.82rem;font-weight:600;color:#0d1b35;line-height:1.4">{a.get('title','')}</div>
                    <div style="font-size:.68rem;color:#94a3b8;margin-top:3px">{a.get('publisher','')} · {time_str}</div>
                </div></a>""", unsafe_allow_html=True)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Vyse entry points ─────────────────────────────────────────────────────
    if data.get("vyse"):
        render_vyse(data["vyse"])


def _vyse_row(label: str, value: str, border_color: str = "#fde68a") -> str:
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:7px 0;border-bottom:1px solid {border_color}">'
        f'<span style="font-size:.75rem;font-weight:600;color:#78350f">{label}</span>'
        f'<span style="font-size:.82rem;font-weight:700;color:#1c1917">{value}</span>'
        f'</div>'
    )

def _vyse_section(title: str) -> str:
    return (
        f'<div style="font-size:.7rem;font-weight:800;letter-spacing:.07em;'
        f'text-transform:uppercase;color:#92400e;margin:12px 0 4px">{title}</div>'
    )

def render_vyse(data: list):
    if not data:
        return
    st.markdown("""
    <div style="background:linear-gradient(135deg,#78350f,#b45309);border-radius:14px;
                padding:16px 22px;margin:20px 0 16px">
        <div style="font-size:.75rem;font-weight:700;letter-spacing:.1em;
                    text-transform:uppercase;opacity:.75;margin-bottom:4px;color:#fef9c3">
            🎯 Vyse — จุดเข้าซื้อ
        </div>
        <div style="font-size:1rem;font-weight:700;color:#fef9c3">
            วิเคราะห์จุดเข้าซื้อและการบริหารความเสี่ยง
        </div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(min(len(data), 3))
    for i, item in enumerate(data):
        with cols[i % len(cols)]:
            ticker = item["ticker"]
            if item.get("error"):
                st.markdown(f"""
                <div style="background:#fffbeb;border:2px solid #f59e0b;border-radius:14px;
                            padding:18px 16px">
                    <div style="font-weight:800;color:#78350f;margin-bottom:8px">{ticker}</div>
                    <div style="font-size:.8rem;color:#92400e">{item['error']}</div>
                </div>""", unsafe_allow_html=True)
                continue

            def _p(v): return f"${v:.2f}" if isinstance(v, (int, float)) else "N/A"

            support_rows = (
                _vyse_row("S1 (ใกล้สุด)",      _p(item.get("s1"))) +
                _vyse_row("S2 (กลาง)",          _p(item.get("s2"))) +
                _vyse_row("S3 (แข็งแกร่งสุด)", _p(item.get("s3")))
            )
            resist_rows = (
                _vyse_row("R1 (เป้าแรก)",    _p(item.get("r1"))) +
                _vyse_row("R2 (เป้ากลาง)",   _p(item.get("r2"))) +
                _vyse_row("R3 (เป้าสูงสุด)", _p(item.get("r3")))
            )
            action_rows = (
                _vyse_row("✅ จุดเข้าซื้อ",  item.get("entry_label", "N/A"), "#f59e0b") +
                _vyse_row("🛑 Stop Loss",     _p(item.get("stop_loss")),      "#f59e0b") +
                _vyse_row("⚖️ ความคุ้มค่า",  f"1:{item.get('rr', 'N/A')}",   "#f59e0b")
            )

            st.markdown(f"""
            <div style="background:linear-gradient(160deg,#fffbeb,#fef3c7);
                        border:2px solid #f59e0b;border-radius:14px;padding:18px 16px;
                        margin-bottom:10px">
                <div style="font-size:1.1rem;font-weight:800;color:#78350f;
                            margin-bottom:8px;padding-bottom:10px;
                            border-bottom:2px solid #f59e0b">{ticker}</div>
                {_vyse_section("🛡️ แนวรับ")}
                {support_rows}
                {_vyse_section("🎯 แนวต้าน")}
                {resist_rows}
                <div style="margin-top:12px;padding-top:4px;border-top:2px solid #f59e0b">
                {action_rows}
                </div>
            </div>""", unsafe_allow_html=True)


def render_result(result):
    if result is None:
        return
    dispatch = {"news": render_news, "price": render_price,
                 "portfolio": render_portfolio, "sage": render_sage}
    dispatch[result["agent"]](result["data"])

# ── main UI ───────────────────────────────────────────────────────────────────

st.title("📊 Portfolio Agent Dashboard")
st.caption("6-agent system — Main Agent routes your commands to the right specialist")
st.markdown("---")

# ── office layout ─────────────────────────────────────────────────────────────
st.markdown('<div class="office-label">Agent Office</div>', unsafe_allow_html=True)

_, main_col, _ = st.columns([1.5, 2, 1.5])
with main_col:
    st.markdown(agent_card("main"), unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

nc, pc, portc, sagec, vysec = st.columns(5)
with nc:    st.markdown(agent_card("news"),      unsafe_allow_html=True)
with pc:    st.markdown(agent_card("price"),     unsafe_allow_html=True)
with portc: st.markdown(agent_card("portfolio"), unsafe_allow_html=True)
with sagec: st.markdown(agent_card("sage"),      unsafe_allow_html=True)
with vysec: st.markdown(agent_card("vyse"),      unsafe_allow_html=True)

st.markdown("---")

# ── results ───────────────────────────────────────────────────────────────────
if st.session_state.last_result:
    target = st.session_state.last_result["agent"]
    st.markdown(f"### {AGENTS[target]['icon']} {AGENTS[target]['label']} — Results")
    render_result(st.session_state.last_result)
    st.markdown("---")

# ── chat ──────────────────────────────────────────────────────────────────────
st.markdown("### 💬 Command Center")

for msg in st.session_state.messages[-14:]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

HINT = "Ask anything… e.g. 'NVDA news', 'show all prices', 'analyze my portfolio', 'show holdings'"
if prompt := st.chat_input(HINT):

    st.session_state.messages.append({"role": "user", "content": prompt})

    # Reset sub-agents, activate main
    for k in ["news", "price", "portfolio", "sage", "vyse"]:
        st.session_state.agent_states[k]["status"] = "idle"
    st.session_state.agent_states["main"]["status"]      = "active"
    st.session_state.agent_states["main"]["last_action"] = f'Routing: "{prompt[:38]}"'

    target = route(prompt)
    st.session_state.agent_states[target]["status"]      = "active"
    st.session_state.agent_states[target]["last_action"] = "Processing…"

    try:
        with st.spinner(f"{AGENTS[target]['icon']} {AGENTS[target]['label']} is working…"):
            if target == "news":
                data        = run_news(prompt)
                tickers_str = ", ".join(d["ticker"] for d in data)
                last_action = f"Fetched headlines for {tickers_str}"
                reply       = f"Latest headlines for **{tickers_str}**"

            elif target == "price":
                data        = run_price(prompt)
                last_action = f"Fetched prices for {len(data)} stock(s)"
                reply       = f"Live prices loaded for **{len(data)} stock(s)**"

            elif target == "portfolio":
                data        = run_portfolio(prompt)
                last_action = f"Loaded {len(data)} holdings"
                reply       = f"Showing **{len(data)} holdings** from portfolio.csv"

            elif target == "sage":
                st.session_state.agent_states["news"]["status"]       = "active"
                st.session_state.agent_states["news"]["last_action"]  = "Fetching headlines for Sage…"
                st.session_state.agent_states["price"]["status"]      = "active"
                st.session_state.agent_states["price"]["last_action"] = "Fetching prices for Sage…"
                st.session_state.agent_states["vyse"]["status"]       = "active"
                st.session_state.agent_states["vyse"]["last_action"]  = "Waiting for Sage data…"
                data        = run_sage(prompt)
                n           = data["total_articles"]
                tickers_str = ", ".join(data["tickers_covered"])
                st.session_state.agent_states["news"]["last_action"]  = f"Passed {n} articles to Sage"
                st.session_state.agent_states["price"]["last_action"] = f"Passed prices for {tickers_str} to Sage"
                st.session_state.agent_states["vyse"]["last_action"]  = f"Entry points calculated for {tickers_str}"
                last_action = f"Briefing ready — {n} articles · {tickers_str}"
                reply       = f"Briefing ready — **{n} articles + live prices + entry points** across {tickers_str}"

        st.session_state.last_result                          = {"agent": target, "data": data}
        st.session_state.agent_states[target]["last_action"]  = last_action
        st.session_state.agent_states[target]["status"]       = "active"
        st.session_state.agent_states["main"]["status"]       = "idle"
        st.session_state.agent_states["main"]["last_action"]  = f"Routed → {AGENTS[target]['label']}"
        # Keep Tracker + Price Agent green when Sage pipeline ran
        if target == "sage":
            st.session_state.agent_states["news"]["status"]  = "active"
            st.session_state.agent_states["price"]["status"] = "active"
            st.session_state.agent_states["vyse"]["status"]  = "active"

        st.session_state.messages.append({
            "role": "assistant",
            "content": f"{AGENTS[target]['icon']} **{AGENTS[target]['label']}** → {reply}",
        })

    except Exception as e:
        st.session_state.agent_states[target]["last_action"] = f"Error: {str(e)[:42]}"
        st.session_state.agent_states["main"]["status"]      = "idle"
        st.session_state.agent_states["main"]["last_action"] = "Error — see chat"
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"❌ {AGENTS[target]['label']} error: {e}",
        })

    st.rerun()
