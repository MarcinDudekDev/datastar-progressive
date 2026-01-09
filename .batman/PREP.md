# Batman Plan: Stock Ticker Demo

## Mission
Build a Bloomberg-style real-time stock ticker streaming fake prices via SSE with flash animations.

## Reconnaissance
- Files explored: 10
- Key findings:
  - main.py has FastAPI + DatastarResponse pattern (lines 35-82 show typewriter SSE)
  - typewriter.html shows data-signals, data-init, data-text pattern
  - Dark theme uses Pico CSS + custom styles
  - SSE.patch_signals() streams signal updates

## Files Inventory

### To Read
| File | Purpose |
|------|---------|
| main.py | Existing SSE patterns |
| templates/typewriter.html | DataStar binding patterns |

### To Modify/Create
| File | Action | Risk |
|------|--------|------|
| main.py | Append 2 endpoints | Low |
| templates/ticker.html | Create new | Low |
| templates/index.html | Add link | Low |

## Subtasks
| # | Task | Model | Target |
|---|------|-------|--------|
| 1 | Create ticker.html template | sonnet | templates/ticker.html |
| 2 | Add /ticker and /stream-ticker endpoints | sonnet | main.py |
| 3 | Add ticker link to index.html | haiku | templates/index.html |

## Architecture

### Price Generator Logic
```python
stocks = [
    {"symbol": "DSTR", "name": "DataStar Inc", "price": 127.50},
    {"symbol": "HTMX", "name": "Hypermedia Corp", "price": 89.25},
    {"symbol": "PYTH", "name": "Python Holdings", "price": 245.00},
    {"symbol": "FAST", "name": "FastAPI Ltd", "price": 156.75},
    {"symbol": "PICO", "name": "PicoCSS Group", "price": 42.00},
]
# Each tick: price += random.uniform(-2, 2)
# Signal includes: symbol, price, change_direction (up/down/none)
```

### HTML Structure
```html
<table data-signals='{"stocks": [...]}'>
  <tr data-for="stock in $stocks">
    <td data-text="$stock.symbol"></td>
    <td data-text="$stock.price"
        data-class='{"flash-up": $stock.dir=="up", "flash-down": $stock.dir=="down"}'></td>
  </tr>
</table>
```

### CSS Flash Animation
```css
.flash-up { animation: flash-green 0.5s; }
.flash-down { animation: flash-red 0.5s; }
@keyframes flash-green { from { background: #00ff00; } }
@keyframes flash-red { from { background: #ff0000; } }
```

## Risks
- data-for may need exact syntax check (DataStar 1.0 RC7)
- Flash animation timing vs SSE update rate

## Execution Notes
- Subtasks 1 and 2 can run in parallel
- Subtask 3 depends on nothing
- Test by running `uvicorn main:app --reload` and visiting /ticker
