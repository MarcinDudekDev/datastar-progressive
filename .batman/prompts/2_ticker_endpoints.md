# Subtask 2: Add Ticker Endpoints to main.py

## Permissions
Read: ANY file
Write: ONLY .batman/outputs/2_ticker_endpoints.txt

## Context
Project: DataStar progressive loading demos
Read .batman/context.json for full context.

## Task
Add two new endpoints to main.py for the stock ticker demo.

## Files to Read
- /Users/cminds/PycharmProjects/datastar-progressive/main.py (MUST read - output is complete replacement)
- /Users/cminds/PycharmProjects/datastar-progressive/.batman/context.json

## Requirements

### New Import
Add `import random` at top.

### Endpoint 1: GET /ticker
```python
@app.get("/ticker", response_class=HTMLResponse)
async def ticker_page(request: Request):
    """Serve the stock ticker demo"""
    return templates.TemplateResponse("ticker.html", {"request": request})
```

### Endpoint 2: GET /stream-ticker
SSE endpoint that streams stock price updates.

```python
# Stock data (module level, above endpoints)
STOCKS = [
    {"symbol": "DSTR", "name": "DataStar Inc", "price": 127.50},
    {"symbol": "HTMX", "name": "Hypermedia Corp", "price": 89.25},
    {"symbol": "PYTH", "name": "Python Holdings", "price": 245.00},
    {"symbol": "FAST", "name": "FastAPI Ltd", "price": 156.75},
    {"symbol": "PICO", "name": "PicoCSS Group", "price": 42.00},
]

@app.get("/stream-ticker")
async def stream_ticker():
    """Stream stock prices with random fluctuations"""
    async def generate():
        prices = {s["symbol"]: s["price"] for s in STOCKS}

        while True:
            stocks_data = []
            for stock in STOCKS:
                sym = stock["symbol"]
                old_price = prices[sym]
                change = random.uniform(-1.5, 1.5)
                new_price = max(1.0, old_price + change)
                prices[sym] = new_price

                direction = "up" if new_price > old_price else "down" if new_price < old_price else "none"
                change_pct = ((new_price - old_price) / old_price) * 100

                stocks_data.append({
                    "symbol": sym,
                    "name": stock["name"],
                    "price": f"${new_price:.2f}",
                    "change": f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%",
                    "dir": direction
                })

            yield SSE.patch_signals({"stocks": stocks_data})
            await asyncio.sleep(1.0)  # Update every second

    return DatastarResponse(generate())
```

## Important
- Keep ALL existing code (index, typewriter, load_stage endpoints)
- Add new endpoints AFTER existing ones, BEFORE `if __name__ == "__main__"`
- Add STOCKS list after templates = ... line

## Output
Write the COMPLETE main.py file to: .batman/outputs/2_ticker_endpoints.txt

Include all existing code plus new additions. Do not omit anything.
