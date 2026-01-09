#!/bin/bash
# Test compression difference for SSE stream

echo "=== WITHOUT COMPRESSION ==="
timeout 3 curl -s -H "Accept-Encoding: identity" http://localhost:8001/stream-typewriter 2>/dev/null | wc -c

echo ""
echo "=== WITH BROTLI ==="
timeout 3 curl -s -H "Accept-Encoding: br" http://localhost:8001/stream-typewriter 2>/dev/null | wc -c

echo ""
echo "=== WITH GZIP ==="
timeout 3 curl -s -H "Accept-Encoding: gzip" http://localhost:8001/stream-typewriter 2>/dev/null | wc -c
