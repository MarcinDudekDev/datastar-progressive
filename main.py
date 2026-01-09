from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.fastapi import DatastarResponse
import asyncio
import random

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Stock data - matches ticker.html frontend
STOCKS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "price": 178.50},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "price": 141.25},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "price": 378.00},
    {"symbol": "TSLA", "name": "Tesla Inc.", "price": 248.75},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "price": 178.00},
]


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
    """Stream stock prices with random fluctuations as flat signals"""
    import time
    async def generate():
        prices = {s["symbol"]: s["price"] for s in STOCKS}

        while True:
            signals = {}
            ts = int(time.time() * 1000)  # Timestamp to force animation re-trigger

            for stock in STOCKS:
                sym = stock["symbol"]
                old_price = prices[sym]
                change = random.uniform(-2.0, 2.0)
                new_price = max(1.0, old_price + change)
                prices[sym] = new_price

                direction = "up" if new_price > old_price else "down" if new_price < old_price else ""
                change_pct = ((new_price - old_price) / old_price) * 100

                # Flat signals per stock: AAPL_price, AAPL_change, etc.
                signals[f"{sym}_symbol"] = sym
                signals[f"{sym}_name"] = stock["name"]
                signals[f"{sym}_price"] = f"${new_price:.2f}"
                signals[f"{sym}_change"] = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
                signals[f"{sym}_dir"] = direction
                signals[f"{sym}_ts"] = ts

            yield SSE.patch_signals(signals)
            await asyncio.sleep(1.0)

    return DatastarResponse(generate())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
