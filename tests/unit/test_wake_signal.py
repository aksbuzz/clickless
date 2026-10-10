"""WakeSignal hands out wake-ups to waiting threads without losing any."""
import threading
import time

from src.engine.worker import WakeSignal


def test_a_wake_before_the_wait_is_not_lost():
    signal = WakeSignal()
    signal.wake(1)
    assert signal.wait(timeout=0.01) is True
    assert signal.wait(timeout=0.01) is False          # the token was used up


def test_wait_times_out_without_a_wake():
    started = time.monotonic()
    assert WakeSignal().wait(timeout=0.1) is False
    assert 0.09 <= time.monotonic() - started < 1.0


def test_one_wake_releases_exactly_one_waiter():
    signal, woken = WakeSignal(), []

    def waiter():
        woken.append(signal.wait(timeout=1.0))

    threads = [threading.Thread(target=waiter) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    signal.wake(1)
    for t in threads:
        t.join()
    assert sorted(woken) == [False, False, True]


def test_wake_many_releases_that_many_waiters():
    signal, woken = WakeSignal(), []

    def waiter():
        woken.append(signal.wait(timeout=1.0))

    threads = [threading.Thread(target=waiter) for _ in range(4)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    signal.wake(3)
    for t in threads:
        t.join()
    assert woken.count(True) == 3
