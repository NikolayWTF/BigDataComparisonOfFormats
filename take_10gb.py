from datasets import load_dataset
import orjson
from pathlib import Path
from tqdm import tqdm

DATASET = "fddemarco/pushshift-reddit-comments"
SPLIT = "train"
OUT = Path("reddit_10gb.jsonl")
TARGET_BYTES = 10 * 1024**3  # 10 GiB

# streaming=True не скачивает всё сразу
ds = load_dataset(DATASET, split=SPLIT, streaming=True)

written = 0
rows = 0

with OUT.open("wb") as f:
    pbar = tqdm(total=TARGET_BYTES, unit="B", unit_scale=True, desc="Writing")
    for ex in ds:
        line = orjson.dumps(ex) + b"\n"
        if written + len(line) > TARGET_BYTES:
            break
        f.write(line)
        written += len(line)
        rows += 1
        pbar.update(len(line))
    pbar.close()

print(f"Done: {OUT}")
print(f"Rows: {rows}")
print(f"Bytes: {written} ({written/1024**3:.2f} GiB)")