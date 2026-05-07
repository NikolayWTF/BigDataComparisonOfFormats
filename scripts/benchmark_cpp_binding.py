import sys
import time
from pathlib import Path

DATA_PATH = Path("data/raw/reddit_10gb.jsonl")

sys.path.append("cpp_bindings")

import fast_count


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    t0 = time.perf_counter()
    lines = fast_count.count_lines(DATA_PATH.as_posix())
    elapsed = time.perf_counter() - t0

    print("C++ binding benchmark")
    print(f"Rows counted: {lines:,}")
    print(f"Elapsed time: {elapsed:.4f} sec")


if __name__ == "__main__":
    main()
