from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.fastapi import DatastarResponse
import asyncio
import yfinance as yf
import httpx

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the progressive loading demo"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/typewriter", response_class=HTMLResponse)
async def typewriter_page(request: Request):
    """Serve the typewriter demo"""
    return templates.TemplateResponse("typewriter.html", {"request": request})


@app.get("/load/{stage}")
async def load_stage(stage: str, request: Request):
    """SSE endpoint to load a stage fragment with slight delay for visual effect"""
    async def generate():
        await asyncio.sleep(0.3)  # Slight delay for unpacking effect
        stage_html = templates.get_template(f"stages/{stage}.html").render({"request": request})
        yield SSE.patch_elements(stage_html)
        yield SSE.patch_signals({"current_stage": stage})

    return DatastarResponse(generate())


@app.get("/stream-typewriter")
async def stream_typewriter():
    """Stream content character by character like a typewriter"""
    async def generate():
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
            yield SSE.patch_signals({"content": accumulated})
            await asyncio.sleep(0.015)  # 15ms for faster typing

    return DatastarResponse(generate())


@app.get("/ticker", response_class=HTMLResponse)
async def ticker_page(request: Request):
    """Serve the stock ticker demo"""
    return templates.TemplateResponse("ticker.html", {"request": request})


@app.get("/stream-ticker")
async def stream_ticker():
    """Stream real stock prices from Yahoo Finance"""
    import time
    async def generate():
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

                yield SSE.patch_signals(signals)
            except Exception as e:
                print(f"Error fetching prices: {e}")

            await asyncio.sleep(5.0)  # Poll every 5 seconds (be nice to Yahoo)

    return DatastarResponse(generate())


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    """Serve the live search demo"""
    return templates.TemplateResponse("search.html", {"request": request})


@app.get("/search-words")
async def search_words(request: Request):
    """Search dictionary and stream results as HTML"""
    # DataStar sends signals in 'datastar' JSON param
    import json
    datastar_param = request.query_params.get("datastar", "{}")
    signals = json.loads(datastar_param)
    q = signals.get("$q", "") or signals.get("q", "")

    async def generate():
        if len(q) < 2:
            html = '<div id="results"><p style="color:#666">Type at least 2 characters...</p></div>'
            yield SSE.patch_elements(html)
            yield SSE.patch_signals({"count": 0})
            return

        # Case-insensitive search
        query = q.lower()
        all_matches = [w for w in WORDS if query in w.lower()]
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
        yield SSE.patch_elements(html)
        yield SSE.patch_signals({"count": len(all_matches)})

    return DatastarResponse(generate())


@app.get("/define/{word}")
async def define_word(word: str):
    """Fetch word definition from free dictionary API"""
    async def generate():
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
        yield SSE.patch_elements(html)

    return DatastarResponse(generate())


@app.get("/clear-def")
async def clear_definition():
    """Clear the definition display"""
    async def generate():
        yield SSE.patch_elements('<div id="definition"></div>')
    return DatastarResponse(generate())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
