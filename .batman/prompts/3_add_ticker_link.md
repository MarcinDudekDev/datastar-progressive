# Subtask 3: Add Ticker Link to index.html

## Permissions
Read: ANY file
Write: ONLY .batman/outputs/3_add_ticker_link.txt

## Context
Project: DataStar progressive loading demos

## Task
Add a navigation link to the stock ticker demo in the index.html page.

## Files to Read
- /Users/cminds/PycharmProjects/datastar-progressive/templates/index.html (MUST read - output is replacement)

## Requirements
Add a small navigation section after the closing `</div>` of #app but before `</main>`:

```html
<nav style="margin-top: 2rem; text-align: center;">
  <a href="/typewriter">Typewriter Demo</a> |
  <a href="/ticker">Stock Ticker Demo</a>
</nav>
```

## Output
Write the COMPLETE index.html file to: .batman/outputs/3_add_ticker_link.txt

Keep all existing code, just add the nav section.
