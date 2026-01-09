from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.fastapi import DatastarResponse
import asyncio
import yfinance as yf

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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
    """SSE endpoint to load a stage fragment"""
    async def generate():
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
                        old_price = prev_prices.get(sym, price)
                        prev_prices[sym] = price

                        # Direction based on previous fetch (for flash animation)
                        direction = "up" if price > old_price else "down" if price < old_price else ""
                        # Change % based on previous close (market change)
                        change_pct = ((price - prev_close) / prev_close) * 100 if prev_close else 0

                        signals[f"{sym}_symbol"] = sym
                        signals[f"{sym}_name"] = STOCK_NAMES[sym]
                        signals[f"{sym}_price"] = f"${price:.2f}"
                        signals[f"{sym}_change"] = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
                        signals[f"{sym}_dir"] = direction
                        signals[f"{sym}_ts"] = ts

                yield SSE.patch_signals(signals)
            except Exception as e:
                print(f"Error fetching prices: {e}")

            await asyncio.sleep(5.0)  # Poll every 5 seconds (be nice to Yahoo)

    return DatastarResponse(generate())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
