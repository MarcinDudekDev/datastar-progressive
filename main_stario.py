"""
DataStar Progressive Loading Demos - Stario 2.0 Version

Run with: uv run python main_stario.py
"""
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import yfinance as yf
from jinja2 import Environment, FileSystemLoader
from stario import Context, RichTracer, Stario, Writer
from stario.html import SafeString

# Jinja2 templates (keeping existing templates)
templates = Environment(loader=FileSystemLoader("templates"))

# Load dictionary at startup
with open("/usr/share/dict/words") as f:
    WORDS = [w.strip() for w in f.readlines()]

# Stock symbols and names
STOCK_NAMES = {
    "AAPL": "Apple Inc.",
    "GOOGL": "Alphabet Inc.",
    "MSFT": "Microsoft Corp.",
    "TSLA": "Tesla Inc.",
    "AMZN": "Amazon.com Inc.",
}

# RSVP Reader state (simple global for demo)
rsvp_state = {
    "words": [],
    "position": 0,
    "wpm": 300,
    "running": False,
    "task": None,
}


def calculate_orp(word: str) -> int:
    """Calculate Optimal Recognition Point for a word."""
    length = len(word)
    if length <= 1:
        return 0
    elif length <= 5:
        return 1
    elif length <= 9:
        return 2
    elif length <= 13:
        return 3
    else:
        return 4


# =============================================================================
# Page Routes (HTML responses)
# =============================================================================


async def index(c: Context, w: Writer) -> None:
    """Serve the progressive loading demo"""
    w.respond(templates.get_template("index.html").render().encode(), b"text/html; charset=utf-8")


async def typewriter_page(c: Context, w: Writer) -> None:
    """Serve the typewriter demo"""
    w.respond(templates.get_template("typewriter.html").render().encode(), b"text/html; charset=utf-8")


async def ticker_page(c: Context, w: Writer) -> None:
    """Serve the stock ticker demo"""
    w.respond(templates.get_template("ticker.html").render().encode(), b"text/html; charset=utf-8")


async def search_page(c: Context, w: Writer) -> None:
    """Serve the live search demo"""
    w.respond(templates.get_template("search.html").render().encode(), b"text/html; charset=utf-8")


async def rsvp_page(c: Context, w: Writer) -> None:
    """Serve the RSVP speed reader demo"""
    w.respond(templates.get_template("rsvp.html").render().encode(), b"text/html; charset=utf-8")


# =============================================================================
# SSE Endpoints (streaming responses)
# =============================================================================


async def load_stage(c: Context, w: Writer) -> None:
    """SSE endpoint to load a stage fragment with slight delay for visual effect"""
    stage = c.req.tail or "shell"
    await asyncio.sleep(0.3)  # Slight delay for unpacking effect
    stage_html = templates.get_template(f"stages/{stage}.html").render()
    w.patch(SafeString(stage_html))
    w.sync({"current_stage": stage})


async def stream_typewriter(c: Context, w: Writer) -> None:
    """Stream content character by character like a typewriter"""
    content = """
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║   ██████╗  █████╗ ████████╗ █████╗ ███████╗████████╗ █████╗ ██████╗   ║
║   ██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔══██╗  ║
║   ██║  ██║███████║   ██║   ███████║███████╗   ██║   ███████║██████╔╝  ║
║   ██║  ██║██╔══██║   ██║   ██╔══██║╚════██║   ██║   ██╔══██║██╔══██╗  ║
║   ██████╔╝██║  ██║   ██║   ██║  ██║███████║   ██║   ██║  ██║██║  ██║  ║
║   ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝  ║
║                                                                       ║
║                     The Hypermedia Framework                          ║
║                                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  > Initializing SSE connection...                                     ║
║  > Loading reactive signals...                                        ║
║  > Streaming content character by character...                        ║
║                                                                       ║
║  This entire page is being "typed" via Server-Sent Events.            ║
║  Each character arrives as a separate SSE signal update.              ║
║                                                                       ║
║  Features demonstrated:                                               ║
║    • Real-time signal streaming                                       ║
║    • Character-by-character accumulation                              ║
║    • DataStar's reactive data-text binding                            ║
║    • Zero JavaScript required (just HTML + attributes)                ║
║                                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  "Any sufficiently advanced technology is                             ║
║   indistinguishable from magic."                                      ║
║                                    — Arthur C. Clarke                 ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝

                      ✨ Typewriter effect complete! ✨
"""
    accumulated = ""
    for char in content:
        accumulated += char
        w.sync({"content": accumulated})
        await asyncio.sleep(0.015)  # 15ms for faster typing


async def stream_ticker(c: Context, w: Writer) -> None:
    """Stream real stock prices from Yahoo Finance"""
    symbols = list(STOCK_NAMES.keys())
    prev_prices = {}

    while True:
        signals = {}
        ts = int(time.time() * 1000)

        try:
            # Fetch real prices from Yahoo Finance
            tickers = yf.Tickers(" ".join(symbols))
            for sym in symbols:
                info = tickers.tickers[sym].info
                price = info.get("regularMarketPrice", 0) or info.get("currentPrice", 0)
                prev_close = info.get("regularMarketPreviousClose", price)

                if price:
                    # Change % based on previous close (daily market change)
                    change_pct = ((price - prev_close) / prev_close) * 100 if prev_close else 0
                    # Direction for colors based on daily change
                    daily_dir = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
                    # Flash only on fetch-to-fetch change
                    old_price = prev_prices.get(sym, price)
                    flash = price != old_price
                    prev_prices[sym] = price

                    signals[f"{sym}_symbol"] = sym
                    signals[f"{sym}_name"] = STOCK_NAMES[sym]
                    signals[f"{sym}_price"] = f"${price:.2f}"
                    signals[f"{sym}_change"] = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
                    signals[f"{sym}_dir"] = daily_dir  # For color
                    signals[f"{sym}_ts"] = ts if flash else 0  # Only flash on actual change

            w.sync(signals)
        except Exception as e:
            print(f"Error fetching prices: {e}")

        await asyncio.sleep(5.0)  # Poll every 5 seconds (be nice to Yahoo)


async def search_words(c: Context, w: Writer) -> None:
    """Search dictionary and stream results as HTML"""
    # Get raw signals dict - DataStar sends keys with $ prefix
    signals = await c.signals()
    q = signals.get("$q", "")

    if len(q) < 2:
        html = '<div id="results"><p style="color:#666">Type at least 2 characters...</p></div>'
        w.patch(SafeString(html))
        w.sync({"count": 0})
        return

    # Case-insensitive search
    query = q.lower()
    all_matches = [word for word in WORDS if query in word.lower()]
    matches = all_matches[:100]

    # Build results HTML with query highlighted
    items = []
    for word in matches:
        # Highlight matching part
        idx = word.lower().find(query)
        if idx >= 0:
            highlighted = f"{word[:idx]}<mark>{word[idx:idx+len(query)]}</mark>{word[idx+len(query):]}"
        else:
            highlighted = word
        items.append(f'<li>{highlighted} <span class="def-btn" data-on:click="@get(\'/define/{word}\')" title="Get definition">?</span></li>')

    html = f'<div id="results"><ul>{"".join(items)}</ul></div>'
    w.patch(SafeString(html))
    w.sync({"count": len(all_matches)})


async def define_word(c: Context, w: Writer) -> None:
    """Fetch word definition from free dictionary API"""
    word = c.req.tail or ""

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                meanings = data[0].get("meanings", [])
                defs = []
                for m in meanings[:2]:  # Max 2 parts of speech
                    pos = m.get("partOfSpeech", "")
                    for d in m.get("definitions", [])[:2]:  # Max 2 definitions each
                        defs.append(f"<em>({pos})</em> {d['definition']}")
                definition = "<br>".join(defs) if defs else "No definition found"
            else:
                definition = "Definition not found in dictionary"
        except Exception:
            definition = "Could not fetch definition"

    html = f'<div id="definition"><strong>{word}</strong>: {definition} <span class="close-def" data-on:click="@get(\'/clear-def\')">×</span></div>'
    w.patch(SafeString(html))


async def clear_definition(c: Context, w: Writer) -> None:
    """Clear the definition display"""
    w.patch(SafeString('<div id="definition"></div>'))


# =============================================================================
# RSVP Speed Reader
# =============================================================================


def get_word_parts(word: str) -> dict:
    """Split word into before, orp (red letter), and after parts."""
    if not word:
        return {"before": "", "orp": "", "after": "", "word": ""}
    orp_idx = calculate_orp(word)
    return {
        "before": word[:orp_idx],
        "orp": word[orp_idx] if orp_idx < len(word) else "",
        "after": word[orp_idx + 1:] if orp_idx + 1 < len(word) else "",
        "word": word,
    }


async def rsvp_start(c: Context, w: Writer) -> None:
    """Start or resume the RSVP reader."""
    global rsvp_state

    # Get text from signals
    signals = await c.signals()
    text = signals.get("$text", "")

    # Parse words if new text or reset
    if text and (not rsvp_state["words"] or rsvp_state["position"] == 0):
        # Split on whitespace, filter empty
        import re
        rsvp_state["words"] = [w for w in re.split(r'\s+', text.strip()) if w]
        rsvp_state["position"] = 0

    if not rsvp_state["words"]:
        return

    rsvp_state["running"] = True
    total = len(rsvp_state["words"])

    # Stream words at WPM rate
    while rsvp_state["running"] and rsvp_state["position"] < total:
        word = rsvp_state["words"][rsvp_state["position"]]
        parts = get_word_parts(word)

        # Calculate delay from WPM (words per minute -> seconds per word)
        delay = 60.0 / rsvp_state["wpm"]

        w.sync({
            **parts,
            "wpm": rsvp_state["wpm"],
            "progress": (rsvp_state["position"] + 1) / total,
            "current_word": rsvp_state["position"] + 1,
            "total_words": total,
            "running": True,
        })

        rsvp_state["position"] += 1
        await asyncio.sleep(delay)

    # Finished or paused
    if rsvp_state["position"] >= total:
        rsvp_state["running"] = False
        w.sync({"running": False, "progress": 1.0})


async def rsvp_pause(c: Context, w: Writer) -> None:
    """Pause the RSVP reader."""
    global rsvp_state
    rsvp_state["running"] = False
    w.sync({"running": False})


async def rsvp_reset(c: Context, w: Writer) -> None:
    """Reset the RSVP reader."""
    global rsvp_state
    rsvp_state["running"] = False
    rsvp_state["position"] = 0
    rsvp_state["words"] = []
    rsvp_state["wpm"] = 300
    w.sync({
        "word": "",
        "before": "",
        "orp": "",
        "after": "",
        "wpm": 300,
        "progress": 0,
        "running": False,
        "current_word": 0,
        "total_words": 0,
    })


async def rsvp_slower(c: Context, w: Writer) -> None:
    """Decrease reading speed."""
    global rsvp_state
    rsvp_state["wpm"] = max(100, rsvp_state["wpm"] - 50)
    w.sync({"wpm": rsvp_state["wpm"]})


async def rsvp_faster(c: Context, w: Writer) -> None:
    """Increase reading speed."""
    global rsvp_state
    rsvp_state["wpm"] = min(1200, rsvp_state["wpm"] + 50)
    w.sync({"wpm": rsvp_state["wpm"]})


# =============================================================================
# App
# =============================================================================


async def main():
    with RichTracer() as tracer:
        app = Stario(tracer)

        # Routes
        app.get("/", index)
        app.get("/typewriter", typewriter_page)
        app.get("/ticker", ticker_page)
        app.get("/search", search_page)
        app.get("/rsvp", rsvp_page)
        app.get("/load/*", load_stage)
        app.get("/stream-typewriter", stream_typewriter)
        app.get("/stream-ticker", stream_ticker)
        app.get("/search-words", search_words)
        app.get("/define/*", define_word)
        app.get("/clear-def", clear_definition)
        app.get("/rsvp/start", rsvp_start)
        app.get("/rsvp/pause", rsvp_pause)
        app.get("/rsvp/reset", rsvp_reset)
        app.get("/rsvp/slower", rsvp_slower)
        app.get("/rsvp/faster", rsvp_faster)

        print("Starting Stario server at http://127.0.0.1:8001")
        await app.serve(host="127.0.0.1", port=8001)


if __name__ == "__main__":
    asyncio.run(main())
