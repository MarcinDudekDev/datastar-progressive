"""
DataStar Progressive Loading Demos - Stario 2.0 Version

Run with: uv run python main_stario.py
"""
import asyncio
import json
import re
import time
import uuid
import zipfile
import io
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import yfinance as yf
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from stario import Context, RichTracer, Stario, Writer
from stario.html import SafeString

# =============================================================================
# Constants
# =============================================================================

DEFAULT_WPM = 300
MIN_WPM = 50
MAX_WPM = 2000
WPM_STEP = 50
SECONDS_PER_MINUTE = 60.0

STAGE_LOAD_DELAY = 0.3
TYPEWRITER_CHAR_DELAY = 0.015
TICKER_POLL_SECONDS = 5.0
API_TIMEOUT_SECONDS = 5.0
URL_IMPORT_TIMEOUT_SECONDS = 15.0

MIN_WORDS_TO_SAVE = 5
MIN_EPUB_WORDS = 10
MIN_ARTICLE_LENGTH = 100
MIN_PARAGRAPH_LENGTH = 50
PREVIEW_LENGTH = 200
MAX_TITLE_LENGTH = 100
TEXT_ID_LENGTH = 8

SEARCH_MIN_CHARS = 2
SEARCH_MAX_RESULTS = 100

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8001

# ORP (Optimal Recognition Point) word-length thresholds
ORP_THRESHOLDS = [(1, 0), (5, 1), (9, 2), (13, 3)]
ORP_DEFAULT = 4

ERROR_PREVIEW_LENGTH = 50

STOCK_NAMES = {
    "AAPL": "Apple Inc.",
    "GOOGL": "Alphabet Inc.",
    "MSFT": "Microsoft Corp.",
    "TSLA": "Tesla Inc.",
    "AMZN": "Amazon.com Inc.",
}

ARTICLE_SELECTORS = [
    "article", "main", '[role="main"]',
    ".post-content", ".article-content", ".entry-content", "#content",
]

NOISE_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "iframe", "noscript"]

# =============================================================================
# Setup
# =============================================================================

templates = Environment(loader=FileSystemLoader("templates"))

with open("/usr/share/dict/words") as f:
    WORDS = [w.strip() for w in f.readlines()]

RSVP_LIBRARY_FILE = Path("rsvp_library.json")


# =============================================================================
# RSVP Library Persistence
# =============================================================================


def load_rsvp_library() -> dict:
    """Load library of texts with per-text state."""
    try:
        if RSVP_LIBRARY_FILE.exists():
            with open(RSVP_LIBRARY_FILE) as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not load library: {e}")
    return {}


def save_rsvp_library() -> None:
    """Persist library to JSON file."""
    try:
        with open(RSVP_LIBRARY_FILE, "w") as f:
            json.dump(rsvp_library, f, indent=2)
    except OSError as e:
        print(f"Warning: Could not save library: {e}")


rsvp_library = load_rsvp_library()
rsvp_state: dict = {
    "text_id": None,
    "words": [],
    "position": 0,
    "wpm": DEFAULT_WPM,
    "running": False,
}


# =============================================================================
# Helpers
# =============================================================================


def calculate_orp(word: str) -> int:
    """Calculate Optimal Recognition Point for a word."""
    length = len(word)
    for max_len, orp in ORP_THRESHOLDS:
        if length <= max_len:
            return orp
    return ORP_DEFAULT


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


def split_into_words(text: str) -> list[str]:
    """Split text into non-empty words."""
    return [w for w in re.split(r'\s+', text.strip()) if w]


def sig(signals: dict, key: str, default: str = "") -> str:
    """Get signal value, handling both '$key' and 'key' formats (RC7/RC8 compat)."""
    return signals.get(f"${key}", signals.get(key, default))


def build_library_items() -> list[dict]:
    """Build sorted library list for UI rendering."""
    items = []
    for text_id, entry in rsvp_library.items():
        items.append({
            "id": text_id,
            "title": entry.get("title", "Untitled"),
            "word_count": len(entry.get("words", [])),
            "position": entry.get("position", 0),
        })
    items.sort(key=lambda x: x["title"].lower())
    return items


# =============================================================================
# Page Routes (HTML responses)
# =============================================================================


async def index(c: Context, w: Writer) -> None:
    """Serve the progressive loading demo."""
    w.respond(templates.get_template("index.html").render().encode(), b"text/html; charset=utf-8")


async def typewriter_page(c: Context, w: Writer) -> None:
    """Serve the typewriter demo."""
    w.respond(templates.get_template("typewriter.html").render().encode(), b"text/html; charset=utf-8")


async def ticker_page(c: Context, w: Writer) -> None:
    """Serve the stock ticker demo."""
    w.respond(templates.get_template("ticker.html").render().encode(), b"text/html; charset=utf-8")


async def search_page(c: Context, w: Writer) -> None:
    """Serve the live search demo."""
    w.respond(templates.get_template("search.html").render().encode(), b"text/html; charset=utf-8")


async def rsvp_page(c: Context, w: Writer) -> None:
    """Serve the RSVP speed reader demo with library."""
    library_items = []
    for text_id, entry in rsvp_library.items():
        library_items.append({
            "id": text_id,
            "title": entry.get("title", "Untitled"),
            "word_count": len(entry.get("words", [])),
            "position": entry.get("position", 0),
            "wpm": entry.get("wpm", DEFAULT_WPM),
        })
    library_items.sort(key=lambda x: x["title"].lower())

    # Check if there's an active session with loaded text (from URL/EPUB import)
    active_session = None
    if rsvp_state.get("words") and not rsvp_state.get("text_id"):
        active_session = {
            "title": rsvp_state.get("pending_title", "Imported Text"),
            "total_words": len(rsvp_state["words"]),
            "position": rsvp_state.get("position", 0),
            "wpm": rsvp_state.get("wpm", DEFAULT_WPM),
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
    """SSE endpoint to load a stage fragment with slight delay for visual effect."""
    stage = c.req.tail or "shell"
    await asyncio.sleep(STAGE_LOAD_DELAY)
    stage_html = templates.get_template(f"stages/{stage}.html").render()
    w.patch(SafeString(stage_html))
    w.sync({"current_stage": stage})


async def stream_typewriter(c: Context, w: Writer) -> None:
    """Stream content character by character like a typewriter."""
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
    # Send full text once, then stream position index (tiny payloads)
    w.sync({"fullText": content})
    for pos in range(1, len(content) + 1):
        w.sync({"pos": pos})
        await asyncio.sleep(TYPEWRITER_CHAR_DELAY)


async def stream_ticker(c: Context, w: Writer) -> None:
    """Stream real stock prices from Yahoo Finance."""
    symbols = list(STOCK_NAMES.keys())
    prev_prices: dict[str, float] = {}

    while True:
        signals = {}
        ts = int(time.time() * 1000)

        try:
            tickers = yf.Tickers(" ".join(symbols))
            for sym in symbols:
                info = tickers.tickers[sym].info
                price = info.get("regularMarketPrice", 0) or info.get("currentPrice", 0)
                prev_close = info.get("regularMarketPreviousClose", price)

                if price:
                    change_pct = ((price - prev_close) / prev_close) * 100 if prev_close else 0
                    daily_dir = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
                    old_price = prev_prices.get(sym, price)
                    flash = price != old_price
                    prev_prices[sym] = price

                    signals[f"{sym}_symbol"] = sym
                    signals[f"{sym}_name"] = STOCK_NAMES[sym]
                    signals[f"{sym}_price"] = f"${price:.2f}"
                    signals[f"{sym}_change"] = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
                    signals[f"{sym}_dir"] = daily_dir
                    signals[f"{sym}_ts"] = ts if flash else 0

            w.sync(signals)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            print(f"Error fetching prices: {e}")

        await asyncio.sleep(TICKER_POLL_SECONDS)


async def search_words(c: Context, w: Writer) -> None:
    """Search dictionary and stream results as HTML."""
    signals = await c.signals()
    q = sig(signals, "q")

    if len(q) < SEARCH_MIN_CHARS:
        html = '<div id="results"><p style="color:#666">Type at least 2 characters...</p></div>'
        w.patch(SafeString(html))
        w.sync({"count": 0})
        return

    query = q.lower()
    all_matches = [word for word in WORDS if query in word.lower()]
    matches = all_matches[:SEARCH_MAX_RESULTS]

    items = []
    for word in matches:
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
    """Fetch word definition from free dictionary API."""
    word = c.req.tail or ""

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                timeout=API_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            meanings = data[0].get("meanings", [])
            defs = []
            for m in meanings[:2]:
                pos = m.get("partOfSpeech", "")
                for d in m.get("definitions", [])[:2]:
                    defs.append(f"<em>({pos})</em> {d['definition']}")
            definition = "<br>".join(defs) if defs else "No definition found"
        except httpx.HTTPStatusError:
            definition = "Definition not found in dictionary"
        except (httpx.HTTPError, KeyError, IndexError):
            definition = "Could not fetch definition"

    html = f'<div id="definition"><strong>{word}</strong>: {definition} <span class="close-def" data-on:click="@get(\'/clear-def\')">×</span></div>'
    w.patch(SafeString(html))


async def clear_definition(c: Context, w: Writer) -> None:
    """Clear the definition display."""
    w.patch(SafeString('<div id="definition"></div>'))


# =============================================================================
# RSVP Speed Reader
# =============================================================================


async def rsvp_start(c: Context, w: Writer) -> None:
    """Start or resume the RSVP reader."""
    global rsvp_state

    if not rsvp_state.get("words"):
        w.sync({"running": False})
        return

    rsvp_state["running"] = True
    total = len(rsvp_state["words"])

    while rsvp_state["running"] and rsvp_state["position"] < total:
        word = rsvp_state["words"][rsvp_state["position"]]
        parts = get_word_parts(word)
        delay = SECONDS_PER_MINUTE / rsvp_state["wpm"]

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

    if rsvp_state["position"] >= total:
        rsvp_state["running"] = False
        w.sync({"running": False, "progress": 1.0, "completed": True, "word": ""})


async def rsvp_pause(c: Context, w: Writer) -> None:
    """Pause the RSVP reader and save position to current text."""
    global rsvp_state
    rsvp_state["running"] = False

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

    text_id = rsvp_state.get("text_id")
    if text_id and text_id in rsvp_library:
        rsvp_library[text_id]["position"] = 0
        save_rsvp_library()

    total = len(rsvp_state.get("words", []))
    w.sync({
        "word": "", "before": "", "orp": "", "after": "",
        "progress": 0, "running": False,
        "current_word": 0, "total_words": total, "completed": False,
    })


async def rsvp_slower(c: Context, w: Writer) -> None:
    """Decrease reading speed."""
    global rsvp_state
    rsvp_state["wpm"] = max(MIN_WPM, rsvp_state["wpm"] - WPM_STEP)
    w.sync({"wpm": rsvp_state["wpm"]})


async def rsvp_faster(c: Context, w: Writer) -> None:
    """Increase reading speed."""
    global rsvp_state
    rsvp_state["wpm"] = min(MAX_WPM, rsvp_state["wpm"] + WPM_STEP)
    w.sync({"wpm": rsvp_state["wpm"]})


async def rsvp_toggle(c: Context, w: Writer) -> None:
    """Pause reading via keyboard shortcut."""
    global rsvp_state
    if rsvp_state["running"]:
        rsvp_state["running"] = False
        w.sync({"running": False})


async def rsvp_set_wpm(c: Context, w: Writer) -> None:
    """Set WPM directly from user input."""
    global rsvp_state
    wpm_str = c.req.query.get("wpm", str(DEFAULT_WPM))
    try:
        wpm = max(MIN_WPM, min(MAX_WPM, int(wpm_str)))
    except ValueError:
        wpm = DEFAULT_WPM
    rsvp_state["wpm"] = wpm
    w.sync({"wpm": wpm})


async def rsvp_library_load(c: Context, w: Writer) -> None:
    """Load a text from library into active reading state."""
    global rsvp_state

    text_id = c.req.tail or ""
    if not text_id or text_id not in rsvp_library:
        w.sync({"error": "Text not found"})
        return

    entry = rsvp_library[text_id]
    words = entry.get("words", [])

    if not words and entry.get("text"):
        words = split_into_words(entry["text"])
        entry["words"] = words
        save_rsvp_library()

    rsvp_state["text_id"] = text_id
    rsvp_state["words"] = words
    rsvp_state["position"] = entry.get("position", 0)
    rsvp_state["wpm"] = entry.get("wpm", DEFAULT_WPM)
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
        "running": False, "completed": False,
        "word": "", "before": "", "orp": "", "after": "",
    })


async def rsvp_library_save(c: Context, w: Writer) -> None:
    """Save text to library with title."""
    global rsvp_state

    title = ""
    text = ""
    try:
        signals = await c.signals()
        title = sig(signals, "saveTitle").strip()
        text = sig(signals, "text").strip()
    except (ValueError, KeyError):
        pass  # May fail with large text — fall back to server-side state

    if not title:
        title = rsvp_state.get("pending_title", "Untitled")

    words = rsvp_state.get("words", [])
    if not text and words:
        text = " ".join(words)
    elif text:
        words = split_into_words(text)

    if not words or len(words) < MIN_WORDS_TO_SAVE:
        w.sync({"error": "Text too short"})
        return

    text_id = str(uuid.uuid4())[:TEXT_ID_LENGTH]
    rsvp_library[text_id] = {
        "title": title,
        "text": text,
        "words": words,
        "position": 0,
        "wpm": rsvp_state.get("wpm", DEFAULT_WPM),
    }
    save_rsvp_library()

    rsvp_state["text_id"] = text_id
    rsvp_state["words"] = words
    rsvp_state["position"] = 0
    rsvp_state["running"] = False

    w.sync({
        "text_id": text_id,
        "title": title,
        "total_words": len(words),
        "current_word": 0,
        "progress": 0,
        "library": build_library_items(),
        "saveTitle": "",
    })


async def rsvp_library_delete(c: Context, w: Writer) -> None:
    """Delete a text from library."""
    global rsvp_state

    text_id = c.req.tail or ""
    if not text_id or text_id not in rsvp_library:
        return

    del rsvp_library[text_id]
    save_rsvp_library()

    was_active = rsvp_state.get("text_id") == text_id
    if was_active:
        rsvp_state["text_id"] = None
        rsvp_state["words"] = []
        rsvp_state["position"] = 0

    w.sync({
        "text_id": None if was_active else rsvp_state.get("text_id"),
        "library": build_library_items(),
        "text": "" if was_active else None,
        "total_words": 0 if was_active else None,
    })


# =============================================================================
# EPUB Parsing
# =============================================================================


def _get_epub_spine(zf: zipfile.ZipFile) -> tuple[str, str, dict, list]:
    """Extract title, OPF directory, manifest, and spine from EPUB zip."""
    container = zf.read("META-INF/container.xml")
    root = ET.fromstring(container)
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile = root.find(".//c:rootfile", ns)
    opf_path = rootfile.get("full-path") if rootfile is not None else "content.opf"

    opf_dir = "/".join(opf_path.split("/")[:-1])
    opf_root = ET.fromstring(zf.read(opf_path))

    title_el = opf_root.find(".//{http://purl.org/dc/elements/1.1/}title")
    title = title_el.text if title_el is not None else "Untitled EPUB"

    manifest: dict[str, str] = {}
    for item in opf_root.findall(".//{http://www.idpf.org/2007/opf}item"):
        item_id = item.get("id")
        href = item.get("href")
        media = item.get("media-type", "")
        if item_id and href and "html" in media:
            manifest[item_id] = href

    spine_ids = []
    for itemref in opf_root.findall(".//{http://www.idpf.org/2007/opf}itemref"):
        idref = itemref.get("idref")
        if idref and idref in manifest:
            spine_ids.append(idref)

    return title, opf_dir, manifest, spine_ids


def _extract_chapter_text(zf: zipfile.ZipFile, opf_dir: str, href: str) -> list[str]:
    """Extract paragraph text from a single EPUB chapter."""
    chapter_path = f"{opf_dir}/{href}" if opf_dir else href
    chapter_html = zf.read(chapter_path).decode("utf-8", errors="ignore")
    soup = BeautifulSoup(chapter_html, "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    return [p.get_text(strip=True) for p in soup.find_all(["p", "h1", "h2", "h3", "h4"]) if p.get_text(strip=True)]


def parse_epub(epub_data: bytes) -> tuple[str, str]:
    """Parse EPUB file and extract title and text."""
    try:
        with zipfile.ZipFile(io.BytesIO(epub_data)) as zf:
            title, opf_dir, manifest, spine_ids = _get_epub_spine(zf)

            all_text: list[str] = []
            for item_id in spine_ids:
                href = manifest[item_id]
                try:
                    all_text.extend(_extract_chapter_text(zf, opf_dir, href))
                except (KeyError, UnicodeDecodeError):
                    continue

            return title, " ".join(all_text)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as e:
        raise ValueError(f"Failed to parse EPUB: {e}") from e


def _extract_epub_from_multipart(body: bytes, content_type: str) -> bytes | None:
    """Extract EPUB file data from multipart form body."""
    if "boundary=" not in content_type:
        return None

    boundary = content_type.split("boundary=")[1].split(";")[0].strip()
    parts = body.split(f"--{boundary}".encode())

    for part in parts:
        if b"filename=" not in part or b".epub" not in part.lower():
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end <= 0:
            continue
        epub_data = part[header_end + len(b"\r\n\r\n"):]
        if epub_data.endswith(b"--\r\n"):
            epub_data = epub_data[:-len(b"--\r\n")]
        elif epub_data.endswith(b"\r\n"):
            epub_data = epub_data[:-len(b"\r\n")]
        return epub_data

    return None


async def rsvp_import_epub(c: Context, w: Writer) -> None:
    """Import EPUB file - returns JSON for JavaScript handling."""
    global rsvp_state

    try:
        body = await c.req.body()
        content_type = c.req.headers.get("content-type", "")
        epub_data = _extract_epub_from_multipart(body, content_type)

        if not epub_data:
            w.respond(json.dumps({"error": "No EPUB file found"}).encode(), b"application/json")
            return

        title, text = parse_epub(epub_data)
        words = split_into_words(text)

        if len(words) < MIN_EPUB_WORDS:
            w.respond(json.dumps({"error": "EPUB has too little text"}).encode(), b"application/json")
            return

        rsvp_state["words"] = words
        rsvp_state["position"] = 0
        rsvp_state["text_id"] = None
        rsvp_state["pending_title"] = title

        preview = text[:PREVIEW_LENGTH] + "..." if len(text) > PREVIEW_LENGTH else text
        w.respond(json.dumps({
            "success": True,
            "title": title,
            "total_words": len(words),
            "preview": preview,
        }).encode(), b"application/json")

    except ValueError as e:
        w.respond(json.dumps({"error": str(e)[:MAX_TITLE_LENGTH]}).encode(), b"application/json")


# =============================================================================
# URL Import
# =============================================================================


async def _fetch_url_content(url: str) -> str:
    """Fetch HTML content from a URL."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=URL_IMPORT_TIMEOUT_SECONDS, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        return resp.text


def _extract_article_text(html: str) -> tuple[str, str]:
    """Extract article title and body text from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Get title
    title = ""
    if soup.title:
        title = soup.title.string or ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    title = re.sub(r'\s+', ' ', title).strip()[:MAX_TITLE_LENGTH]

    # Remove noise elements
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    # Try structured selectors first
    article_text = ""
    for selector in ARTICLE_SELECTORS:
        container = soup.select_one(selector)
        if container:
            paragraphs = container.find_all("p")
            if len(paragraphs) > 2:
                article_text = " ".join(p.get_text(strip=True) for p in paragraphs)
                break

    # Fallback: all substantial paragraphs
    if not article_text or len(article_text) < PREVIEW_LENGTH:
        paragraphs = soup.find_all("p")
        article_text = " ".join(
            p.get_text(strip=True) for p in paragraphs
            if len(p.get_text(strip=True)) > MIN_PARAGRAPH_LENGTH
        )

    return title, re.sub(r'\s+', ' ', article_text).strip()


async def rsvp_import_url(c: Context, w: Writer) -> None:
    """Import article text from a URL."""
    try:
        signals = await c.signals()
        url = sig(signals, "importUrl").strip()
    except (ValueError, KeyError):
        w.sync({"importError": "Could not read URL"})
        return

    if not url or not url.startswith(("http://", "https://")):
        w.sync({"importError": "Please enter a valid URL"})
        return

    try:
        html = await _fetch_url_content(url)
    except httpx.HTTPError as e:
        w.sync({"importError": f"Failed to fetch: {str(e)[:ERROR_PREVIEW_LENGTH]}"})
        return

    title, article_text = _extract_article_text(html)

    if len(article_text) < MIN_ARTICLE_LENGTH:
        w.sync({"importError": "Could not extract article text from this URL"})
        return

    words = split_into_words(article_text)

    rsvp_state["words"] = words
    rsvp_state["position"] = 0
    rsvp_state["text_id"] = None
    rsvp_state["pending_title"] = title or "Imported Article"

    preview = article_text[:PREVIEW_LENGTH] + "..." if len(article_text) > PREVIEW_LENGTH else article_text
    w.sync({
        "importUrl": "",
        "importError": "",
        "title": title or "Imported Article",
        "saveTitle": title or "Imported Article",
        "total_words": len(words),
        "current_word": 0,
        "progress": 0,
        "textPreview": preview,
        "textLoaded": True,
    })


# =============================================================================
# App
# =============================================================================


async def main() -> None:
    with RichTracer() as tracer:
        app = Stario(tracer)

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

        print(f"Starting Stario server at http://{SERVER_HOST}:{SERVER_PORT}")
        await app.serve(host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    asyncio.run(main())
