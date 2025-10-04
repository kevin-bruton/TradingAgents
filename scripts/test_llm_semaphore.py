import os, time, threading
from tradingagents.utils.concurrency import set_max_concurrent, llm_call


def _fake_llm(duration: float, results: list):
    with llm_call():
        time.sleep(duration)
        results.append(time.time())


def test_llm_semaphore_limits_parallelism():
    # Configure semaphore to 2
    set_max_concurrent(2)
    start = time.time()
    results = []
    threads = [threading.Thread(target=_fake_llm, args=(0.25, results)) for _ in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.time() - start
    # With capacity 2 and each taking 0.25s, 3 calls must take at least ~0.50s
    assert elapsed >= 0.48, f"Expected serialized batch behavior, elapsed={elapsed}"