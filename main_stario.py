"""
DataStar Progressive Loading Demos - Stario 2.0 Version

Run with: uv run python main_stario.py
"""
import asyncio
import json
import time
import zipfile
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import httpx
import yfinance as yf
from bs4 import BeautifulSoup
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

# RSVP Reader state - per-text library with individual positions
RSVP_LIBRARY_FILE = Path("rsvp_library.json")


def load_rsvp_library() -> dict:
    """Load library of texts with per-text state."""
    try:
        if RSVP_LIBRARY_FILE.exists():
            with open(RSVP_LIBRARY_FILE) as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load library: {e}")
    return {}


def save_rsvp_library():
    """Persist library to JSON file."""
    try:
        with open(RSVP_LIBRARY_FILE, "w") as f:
            json.dump(rsvp_library, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save library: {e}")


def get_text_entry(text_id: str) -> dict:
    """Get or create entry for a text."""
    if text_id not in rsvp_library:
        rsvp_library[text_id] = {
            "title": "",
            "text": "",
            "words": [],
            "position": 0,
            "wpm": 300,
        }
    return rsvp_library[text_id]


# Load library and current session state on startup
rsvp_library = load_rsvp_library()
rsvp_state = {
    "text_id": None,  # Currently active text ID
    "words": [],
    "position": 0,
    "wpm": 300,
    "running": False,
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
    """Serve the RSVP speed reader demo with library."""
    # Build library list for dropdown (id, title, word_count, position)
    library_items = []
    for text_id, entry in rsvp_library.items():
        word_count = len(entry.get("words", []))
        library_items.append({
            "id": text_id,
            "title": entry.get("title", "Untitled"),
            "word_count": word_count,
            "position": entry.get("position", 0),
            "wpm": entry.get("wpm", 300),
        })
    # Sort by most recently... we don't track that yet, so just by title
    library_items.sort(key=lambda x: x["title"].lower())

    # Check if there's an active session with loaded text (from URL/EPUB import)
    active_session = None
    if rsvp_state.get("words") and not rsvp_state.get("text_id"):
        # Text loaded but not saved to library yet
        active_session = {
            "title": rsvp_state.get("pending_title", "Imported Text"),
            "total_words": len(rsvp_state["words"]),
            "position": rsvp_state.get("position", 0),
            "wpm": rsvp_state.get("wpm", 300),
        }

    w.respond(
        templates.get_template("rsvp.html").render(
            library=library_items,
            active=active_session,
        ).encode(),
        b"text/html; charset=utf-8"
    )


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

    # If no text loaded, can't start
    if not rsvp_state.get("words"):
        w.sync({"running": False})
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
        w.sync({"running": False, "progress": 1.0, "completed": True, "word": ""})


async def rsvp_pause(c: Context, w: Writer) -> None:
    """Pause the RSVP reader and save position to current text."""
    global rsvp_state
    rsvp_state["running"] = False

    # Save position to current text's library entry
    text_id = rsvp_state.get("text_id")
    if text_id and text_id in rsvp_library:
        rsvp_library[text_id]["position"] = rsvp_state["position"]
        rsvp_library[text_id]["wpm"] = rsvp_state["wpm"]
        save_rsvp_library()

    w.sync({"running": False})


async def rsvp_reset(c: Context, w: Writer) -> None:
    """Reset position for current text (start from beginning)."""
    global rsvp_state
    rsvp_state["running"] = False
    rsvp_state["position"] = 0

    # Reset position in library entry too
    text_id = rsvp_state.get("text_id")
    if text_id and text_id in rsvp_library:
        rsvp_library[text_id]["position"] = 0
        save_rsvp_library()

    total = len(rsvp_state.get("words", []))
    w.sync({
        "word": "",
        "before": "",
        "orp": "",
        "after": "",
        "progress": 0,
        "running": False,
        "current_word": 0,
        "total_words": total,
        "completed": False,
    })


async def rsvp_slower(c: Context, w: Writer) -> None:
    """Decrease reading speed."""
    global rsvp_state
    rsvp_state["wpm"] = max(50, rsvp_state["wpm"] - 50)
    w.sync({"wpm": rsvp_state["wpm"]})


async def rsvp_faster(c: Context, w: Writer) -> None:
    """Increase reading speed."""
    global rsvp_state
    rsvp_state["wpm"] = min(2000, rsvp_state["wpm"] + 50)
    w.sync({"wpm": rsvp_state["wpm"]})


async def rsvp_toggle(c: Context, w: Writer) -> None:
    """Pause reading via keyboard shortcut. Resume requires clicking Start button."""
    global rsvp_state
    if rsvp_state["running"]:
        rsvp_state["running"] = False
        w.sync({"running": False})


async def rsvp_set_wpm(c: Context, w: Writer) -> None:
    """Set WPM directly from user input."""
    global rsvp_state
    # Get wpm from query string
    wpm_str = c.req.query.get("wpm", "300")
    try:
        wpm = max(50, min(2000, int(wpm_str)))
    except ValueError:
        wpm = 300
    rsvp_state["wpm"] = wpm
    w.sync({"wpm": wpm})


async def rsvp_library_load(c: Context, w: Writer) -> None:
    """Load a text from library into active reading state."""
    global rsvp_state
    import re

    text_id = c.req.tail or ""
    if not text_id or text_id not in rsvp_library:
        w.sync({"error": "Text not found"})
        return

    entry = rsvp_library[text_id]
    words = entry.get("words", [])

    # If words not parsed yet, parse from text
    if not words and entry.get("text"):
        words = [w for w in re.split(r'\s+', entry["text"].strip()) if w]
        entry["words"] = words
        save_rsvp_library()

    # Load into active state
    rsvp_state["text_id"] = text_id
    rsvp_state["words"] = words
    rsvp_state["position"] = entry.get("position", 0)
    rsvp_state["wpm"] = entry.get("wpm", 300)
    rsvp_state["running"] = False

    total = len(words)
    position = rsvp_state["position"]

    w.sync({
        "text_id": text_id,
        "title": entry.get("title", "Untitled"),
        "text": entry.get("text", ""),
        "wpm": rsvp_state["wpm"],
        "total_words": total,
        "current_word": position,
        "progress": position / total if total else 0,
        "running": False,
        "completed": False,
        "word": "",
        "before": "",
        "orp": "",
        "after": "",
    })


async def rsvp_library_save(c: Context, w: Writer) -> None:
    """Save text to library with title."""
    global rsvp_state
    import re
    import uuid

    # Get title from signals
    title = ""
    text = ""
    try:
        signals = await c.signals()
        title = signals.get("$saveTitle", "").strip()
        text = signals.get("$text", "").strip()
    except Exception:
        pass  # May fail with large text, use server-side state

    # Use pending_title from URL import if no title from signals
    if not title:
        title = rsvp_state.get("pending_title", "Untitled")

    # If text not in signals, use server-side state (from URL import)
    words = rsvp_state.get("words", [])
    if not text and words:
        # Reconstruct text from words (URL import case)
        text = " ".join(words)
    elif text:
        # Parse words from signal text
        words = [w for w in re.split(r'\s+', text) if w]

    if not words or len(words) < 5:
        w.sync({"error": "Text too short"})
        return

    # Create new entry
    text_id = str(uuid.uuid4())[:8]
    rsvp_library[text_id] = {
        "title": title,
        "text": text,
        "words": words,
        "position": 0,
        "wpm": rsvp_state.get("wpm", 300),
    }
    save_rsvp_library()

    # Load it as active
    rsvp_state["text_id"] = text_id
    rsvp_state["words"] = words
    rsvp_state["position"] = 0
    rsvp_state["running"] = False

    # Return updated library for dropdown
    library_items = []
    for tid, entry in rsvp_library.items():
        library_items.append({
            "id": tid,
            "title": entry.get("title", "Untitled"),
            "word_count": len(entry.get("words", [])),
            "position": entry.get("position", 0),
        })
    library_items.sort(key=lambda x: x["title"].lower())

    w.sync({
        "text_id": text_id,
        "title": title,
        "total_words": len(words),
        "current_word": 0,
        "progress": 0,
        "library": library_items,
        "saveTitle": "",  # Clear input
    })


async def rsvp_library_delete(c: Context, w: Writer) -> None:
    """Delete a text from library."""
    global rsvp_state

    text_id = c.req.tail or ""
    if not text_id or text_id not in rsvp_library:
        return

    del rsvp_library[text_id]
    save_rsvp_library()

    # If we deleted the active text, clear state
    if rsvp_state.get("text_id") == text_id:
        rsvp_state["text_id"] = None
        rsvp_state["words"] = []
        rsvp_state["position"] = 0

    # Return updated library
    library_items = []
    for tid, entry in rsvp_library.items():
        library_items.append({
            "id": tid,
            "title": entry.get("title", "Untitled"),
            "word_count": len(entry.get("words", [])),
            "position": entry.get("position", 0),
        })
    library_items.sort(key=lambda x: x["title"].lower())

    w.sync({
        "text_id": None if rsvp_state.get("text_id") == text_id else rsvp_state.get("text_id"),
        "library": library_items,
        "text": "" if rsvp_state.get("text_id") == text_id else None,
        "total_words": 0 if rsvp_state.get("text_id") == text_id else None,
    })


def parse_epub(epub_data: bytes) -> tuple[str, str]:
    """Parse EPUB file and extract title and text."""
    try:
        with zipfile.ZipFile(io.BytesIO(epub_data)) as zf:
            # Find content.opf via container.xml
            container = zf.read("META-INF/container.xml")
            root = ET.fromstring(container)
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rootfile = root.find(".//c:rootfile", ns)
            opf_path = rootfile.get("full-path") if rootfile is not None else "content.opf"

            # Parse OPF to get spine order and title
            opf_dir = "/".join(opf_path.split("/")[:-1])
            opf_content = zf.read(opf_path)
            opf_root = ET.fromstring(opf_content)

            # Get title
            ns_dc = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
            title_el = opf_root.find(".//{http://purl.org/dc/elements/1.1/}title")
            title = title_el.text if title_el is not None else "Untitled EPUB"

            # Get manifest (id -> href mapping)
            manifest = {}
            for item in opf_root.findall(".//{http://www.idpf.org/2007/opf}item"):
                item_id = item.get("id")
                href = item.get("href")
                media = item.get("media-type", "")
                if item_id and href and "html" in media:
                    manifest[item_id] = href

            # Get spine order
            spine_ids = []
            for itemref in opf_root.findall(".//{http://www.idpf.org/2007/opf}itemref"):
                idref = itemref.get("idref")
                if idref and idref in manifest:
                    spine_ids.append(idref)

            # Extract text from chapters in order
            all_text = []
            for item_id in spine_ids:
                href = manifest[item_id]
                chapter_path = f"{opf_dir}/{href}" if opf_dir else href
                try:
                    chapter_html = zf.read(chapter_path).decode("utf-8", errors="ignore")
                    soup = BeautifulSoup(chapter_html, "html.parser")
                    # Remove scripts, styles
                    for tag in soup.find_all(["script", "style"]):
                        tag.decompose()
                    # Get text from paragraphs
                    for p in soup.find_all(["p", "h1", "h2", "h3", "h4"]):
                        text = p.get_text(strip=True)
                        if text:
                            all_text.append(text)
                except Exception:
                    continue

            return title, " ".join(all_text)
    except Exception as e:
        raise ValueError(f"Failed to parse EPUB: {e}")


async def rsvp_import_epub(c: Context, w: Writer) -> None:
    """Import EPUB file - returns JSON for JavaScript handling."""
    global rsvp_state

    # Read multipart form data
    try:
        body = await c.req.body()
        # Parse multipart boundary
        content_type = c.req.headers.get("content-type", "")
        if "boundary=" not in content_type:
            w.respond(json.dumps({"error": "Invalid upload format"}).encode(), b"application/json")
            return

        boundary = content_type.split("boundary=")[1].split(";")[0].strip()
        parts = body.split(f"--{boundary}".encode())

        epub_data = None
        for part in parts:
            if b"filename=" in part and b".epub" in part.lower():
                # Find start of file data (after headers)
                header_end = part.find(b"\r\n\r\n")
                if header_end > 0:
                    epub_data = part[header_end + 4:]
                    # Remove trailing boundary markers
                    if epub_data.endswith(b"--\r\n"):
                        epub_data = epub_data[:-4]
                    elif epub_data.endswith(b"\r\n"):
                        epub_data = epub_data[:-2]
                    break

        if not epub_data:
            w.respond(json.dumps({"error": "No EPUB file found"}).encode(), b"application/json")
            return

        title, text = parse_epub(epub_data)
        words = [word for word in re.split(r'\s+', text.strip()) if word]

        if len(words) < 10:
            w.respond(json.dumps({"error": "EPUB has too little text"}).encode(), b"application/json")
            return

        # Store in session state
        rsvp_state["words"] = words
        rsvp_state["position"] = 0
        rsvp_state["text_id"] = None
        rsvp_state["pending_title"] = title

        # Return JSON for JavaScript to handle
        result = {
            "success": True,
            "title": title,
            "total_words": len(words),
            "preview": text[:200] + "..." if len(text) > 200 else text,
        }
        w.respond(json.dumps(result).encode(), b"application/json")

    except Exception as e:
        w.respond(json.dumps({"error": str(e)[:100]}).encode(), b"application/json")


async def rsvp_import_url(c: Context, w: Writer) -> None:
    """Import article text from a URL."""

    # Get URL from signals
    try:
        signals = await c.signals()
        url = signals.get("$importUrl", "").strip()
    except Exception:
        w.sync({"importError": "Could not read URL"})
        return

    if not url or not url.startswith(("http://", "https://")):
        w.sync({"importError": "Please enter a valid URL"})
        return

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=15.0, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        w.sync({"importError": f"Failed to fetch: {str(e)[:50]}"})
        return

    # Parse HTML and extract article text
    soup = BeautifulSoup(html, "html.parser")

    # Get title
    title = ""
    if soup.title:
        title = soup.title.string or ""
    # Try og:title or article title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    # Clean title
    title = re.sub(r'\s+', ' ', title).strip()[:100]

    # Remove unwanted elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "iframe", "noscript"]):
        tag.decompose()

    # Try to find article content
    article_text = ""

    # Look for article tag or common content containers
    for selector in ["article", "main", '[role="main"]', ".post-content", ".article-content", ".entry-content", "#content"]:
        container = soup.select_one(selector)
        if container:
            # Get text from paragraphs
            paragraphs = container.find_all("p")
            if len(paragraphs) > 2:
                article_text = " ".join(p.get_text(strip=True) for p in paragraphs)
                break

    # Fallback: get all paragraphs
    if not article_text or len(article_text) < 200:
        paragraphs = soup.find_all("p")
        article_text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)

    # Clean up text
    article_text = re.sub(r'\s+', ' ', article_text).strip()

    if len(article_text) < 100:
        w.sync({"importError": "Could not extract article text from this URL"})
        return

    # Parse into words
    words = [w for w in re.split(r'\s+', article_text) if w]

    # Store in session state (don't sync full text - too large for SSE)
    rsvp_state["words"] = words
    rsvp_state["position"] = 0
    rsvp_state["text_id"] = None  # Not saved to library yet
    rsvp_state["pending_title"] = title or "Imported Article"  # Save title for later

    # Sync metadata only, plus signal to reload text
    w.sync({
        "importUrl": "",
        "importError": "",
        "title": title or "Imported Article",
        "saveTitle": title or "Imported Article",
        "total_words": len(words),
        "current_word": 0,
        "progress": 0,
        "textPreview": article_text[:200] + "..." if len(article_text) > 200 else article_text,
        "textLoaded": True,
    })


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
        app.get("/rsvp/toggle", rsvp_toggle)
        app.get("/rsvp/set-wpm", rsvp_set_wpm)
        app.get("/rsvp/library/load/*", rsvp_library_load)
        app.get("/rsvp/library/save", rsvp_library_save)
        app.get("/rsvp/library/delete/*", rsvp_library_delete)
        app.get("/rsvp/import-url", rsvp_import_url)
        app.post("/rsvp/import-epub", rsvp_import_epub)

        print("Starting Stario server at http://127.0.0.1:8001")
        await app.serve(host="127.0.0.1", port=8001)


if __name__ == "__main__":
    asyncio.run(main())
