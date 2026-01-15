# DataStar Progressive Loading Demos

Interactive demos showcasing [DataStar](https://data-star.dev/) - the hypermedia framework for building reactive web applications with minimal JavaScript.

## Demos

### 1. Progressive Loading (`/`)
Auto-cascading page assembly where each stage triggers the next via SSE. Watch the UI "unpack" itself automatically.

**Features:** `data-init`, `@get`, `patch_elements`, morphing chain

### 2. Typewriter Effect (`/typewriter`)
Character-by-character streaming via Server-Sent Events. ASCII art banner types itself out in real-time.

**Features:** `data-signals`, `data-text`, signal streaming

### 3. Live Stock Ticker (`/ticker`)
Real-time stock prices from Yahoo Finance with color-coded changes and flash animations.

**Features:** `data-attr:class`, timestamp trick for CSS animation re-triggers

### 4. Dictionary Search (`/search`)
Search 235,976 English words with instant results, highlighting, and inline definitions.

**Features:** `data-bind`, `__debounce-200`, `data-show`, `data-on:click` in morphed content

## Tech Stack

- **Backend:** FastAPI + [datastar-py](https://pypi.org/project/datastar-py/)
- **Frontend:** DataStar + Pico.css (dark theme)
- **Data:** Yahoo Finance API, Free Dictionary API

## Run Locally

```bash
# Install dependencies
pip install fastapi uvicorn datastar-py yfinance httpx

# Start server
uvicorn main:app --port 8001 --reload

# Open http://localhost:8001
```

## Key DataStar Patterns Demonstrated

| Pattern | Example |
|---------|---------|
| Auto-trigger on mount | `data-init="@get('/load/next')"` |
| Two-way binding | `data-bind="$q"` |
| Debounced input | `data-on:input__debounce-200="@get('/search')"` |
| Conditional display | `data-show="$count > 0"` |
| Dynamic classes | `data-attr:class="$dir === 'up' ? 'green' : 'red'"` |
| SSE morphing | `SSE.patch_elements(html)` |
| Signal updates | `SSE.patch_signals({"count": 42})` |

## Learnings

- DataStar sends signals to server with `$` prefix in JSON (`$q` not `q`)
- Use `patch_elements` for HTML fragments, `patch_signals` for reactive state
- Debounce modifier syntax: `__debounce-{ms}` (double underscore)
- Event handlers in morphed content work automatically

## License

MIT
