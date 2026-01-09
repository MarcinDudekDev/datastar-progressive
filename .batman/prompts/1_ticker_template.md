# Subtask 1: Create ticker.html Template

## Permissions
Read: ANY file
Write: ONLY .batman/outputs/1_ticker_template.txt

## Context
Project: DataStar progressive loading demos
Read .batman/context.json for full context.

## Task
Create a Bloomberg-terminal-style stock ticker page using DataStar for real-time updates.

## Files to Read
- /Users/cminds/PycharmProjects/datastar-progressive/templates/typewriter.html (reference for DataStar patterns)
- /Users/cminds/PycharmProjects/datastar-progressive/.batman/context.json (CDN URLs, patterns)

## Requirements

### Visual Design
- Bloomberg terminal aesthetic: dark background (#0d1117), monospace font
- Green (#00ff00) for positive changes, red (#ff3333) for negative
- Table with columns: Symbol, Name, Price, Change
- Terminal-style header with "DATASTAR TERMINAL" title

### DataStar Integration
- data-signals with initial empty stocks array
- data-init="@get('/stream-ticker')" to start SSE
- data-for="stock in $stocks" to iterate stocks
- data-text bindings for each cell
- data-class for flash animations based on stock.dir

### CSS Flash Animations
```css
.flash-up { animation: flash-green 0.3s ease-out; }
.flash-down { animation: flash-red 0.3s ease-out; }
@keyframes flash-green {
  0% { background: rgba(0, 255, 0, 0.4); }
  100% { background: transparent; }
}
@keyframes flash-red {
  0% { background: rgba(255, 0, 0, 0.4); }
  100% { background: transparent; }
}
```

### Structure
```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <!-- Pico CSS + custom styles -->
</head>
<body>
  <main class="container">
    <header>DATASTAR TERMINAL - LIVE PRICES</header>
    <table data-signals='{"stocks": []}' data-init="@get('/stream-ticker')">
      <thead>...</thead>
      <tbody>
        <template data-for="stock in $stocks">
          <tr data-class='{"flash-up": $stock.dir=="up", "flash-down": $stock.dir=="down"}'>
            <td data-text="$stock.symbol"></td>
            <td data-text="$stock.name"></td>
            <td data-text="$stock.price"></td>
            <td data-text="$stock.change" data-class='{"positive": $stock.dir=="up", "negative": $stock.dir=="down"}'></td>
          </tr>
        </template>
      </tbody>
    </table>
    <a href="/">Back to demos</a>
  </main>
  <script type="module" src="[DataStar CDN]"></script>
</body>
</html>
```

## Output
Write the COMPLETE ticker.html file to: .batman/outputs/1_ticker_template.txt

Make it production-ready, visually impressive, Bloomberg-style.
