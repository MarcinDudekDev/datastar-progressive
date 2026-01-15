"""
Benchmark: FastAPI + datastar-py vs Stario 2.0
"""
import subprocess
import time
import httpx
import statistics
import os
import psutil

FASTAPI_PORT = 8000
STARIO_PORT = 8001
ITERATIONS = 50

def get_memory_mb(pid):
    try:
        return psutil.Process(pid).memory_info().rss / 1024 / 1024
    except:
        return 0

def benchmark_endpoint(url, name, iterations=ITERATIONS):
    times = []
    client = httpx.Client(timeout=10.0)

    # Warmup
    for _ in range(3):
        try:
            client.get(url)
        except:
            pass

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            resp = client.get(url)
            elapsed = (time.perf_counter() - start) * 1000
            if resp.status_code == 200:
                times.append(elapsed)
        except Exception as e:
            pass

    client.close()

    if times:
        return {
            "name": name,
            "avg_ms": statistics.mean(times),
            "min_ms": min(times),
            "max_ms": max(times),
            "std_ms": statistics.stdev(times) if len(times) > 1 else 0,
            "count": len(times)
        }
    return None

def count_lines(filepath):
    with open(filepath) as f:
        return len([l for l in f if l.strip() and not l.strip().startswith('#')])

def main():
    print("=" * 60)
    print("BENCHMARK: FastAPI + datastar-py vs Stario 2.0")
    print("=" * 60)

    # Code comparison
    print("\n CODE COMPARISON:")
    fastapi_lines = count_lines("main.py")
    stario_lines = count_lines("main_stario.py")
    print(f"   FastAPI: {fastapi_lines} lines (non-comment)")
    print(f"   Stario:  {stario_lines} lines (non-comment)")
    print(f"   Diff:    {stario_lines - fastapi_lines:+d} lines")

    # File size
    fastapi_size = os.path.getsize("main.py")
    stario_size = os.path.getsize("main_stario.py")
    print(f"\n   FastAPI: {fastapi_size:,} bytes")
    print(f"   Stario:  {stario_size:,} bytes")

    # Endpoint benchmarks
    print(f"\n RESPONSE TIME ({ITERATIONS} requests each):")

    endpoints = [
        ("/", "Home page"),
        ("/search", "Search page"),
    ]

    results = {"fastapi": [], "stario": []}

    for path, name in endpoints:
        # FastAPI
        fa_result = benchmark_endpoint(f"http://127.0.0.1:{FASTAPI_PORT}{path}", f"FastAPI {name}")
        if fa_result:
            results["fastapi"].append(fa_result)

        # Stario
        st_result = benchmark_endpoint(f"http://127.0.0.1:{STARIO_PORT}{path}", f"Stario {name}")
        if st_result:
            results["stario"].append(st_result)

        if fa_result and st_result:
            diff = ((st_result["avg_ms"] - fa_result["avg_ms"]) / fa_result["avg_ms"]) * 100
            faster = "Stario" if diff < 0 else "FastAPI"
            print(f"\n   {name}:")
            print(f"      FastAPI: {fa_result['avg_ms']:.2f}ms (+/-{fa_result['std_ms']:.2f})")
            print(f"      Stario:  {st_result['avg_ms']:.2f}ms (+/-{st_result['std_ms']:.2f})")
            print(f"      Winner:  {faster} ({abs(diff):.1f}% faster)")

    # Memory comparison
    print("\n MEMORY USAGE:")

    # Find PIDs
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmd = ' '.join(proc.info['cmdline'] or [])
            if 'main.py' in cmd and 'python' in cmd and 'stario' not in cmd:
                mem = get_memory_mb(proc.info['pid'])
                print(f"   FastAPI: {mem:.1f} MB")
            elif 'main_stario.py' in cmd and 'python' in cmd:
                mem = get_memory_mb(proc.info['pid'])
                print(f"   Stario:  {mem:.1f} MB")
        except:
            pass

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
