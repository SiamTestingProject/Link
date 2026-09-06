import gc
import ctypes

# Optimize Python GC threshold for low memory / high throughput environments
gc.enable()
gc.set_threshold(400, 5, 5)

def flush_ram():
    """
    Forces Python garbage collector to collect cyclic references and calls 
    Linux glibc malloc_trim(0) to release freed heap pages back to the OS.
    """
    gc.collect()
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass
