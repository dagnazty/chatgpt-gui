# rate_limiter.py

import time
import threading
import logging

class RateLimiter:
    """
    A simple thread-safe token bucket rate limiter.
    """

    def __init__(self, max_calls: int, period: float):
        """
        Initializes the RateLimiter.

        Args:
            max_calls (int): Maximum number of calls allowed within the period.
            period (float): Time period in seconds.
        """
        self.max_calls = max_calls
        self.period = period
        self.tokens = max_calls
        self.lock = threading.Lock()
        self.last_refill = time.time()
        logging.info(f"RateLimiter initialized with max_calls={max_calls}, period={period}s")

    def acquire(self):
        """
        Acquire a token, blocking until one is available.
        """
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_refill

            # Refill tokens based on elapsed time
            refill_amount = (elapsed / self.period) * self.max_calls
            if refill_amount >= 1:
                refill_tokens = int(refill_amount)
                self.tokens = min(self.max_calls, self.tokens + refill_tokens)
                self.last_refill = current_time

            if self.tokens >= 1:
                self.tokens -= 1
                logging.debug(f"Token acquired. Tokens left: {self.tokens}")
                return
            else:
                # Calculate wait time until the next token is available
                wait_time = self.period / self.max_calls
                logging.warning(f"Rate limit exceeded. Sleeping for {wait_time:.2f} seconds.")
        
        # Release the lock before sleeping to allow other threads to proceed
        time.sleep(wait_time)
        self.acquire()  # Retry after sleeping
