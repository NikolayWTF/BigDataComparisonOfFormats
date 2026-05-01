import os
import time
import json
import sqlite3
import pyarrow as pa
import pyarrow.orc as orc
from pathlib import Path
from contextlib import contextmanager

import polars as pl


RAW_PATH = Path("data/raw/reddit_10gb.jsonl")
OUT_DIR = Path("data/converted")
OUT_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_CSV = Path("results/write_benchmark.csv")
RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)

COLUMNS = ["id", "author", "subreddit", "body", "created_utc", "score", "controversiality"]



@contextmanager
def timer():
    t0_wall = time.perf_counter()
    t0_cpu = time.process_time()
    yield lambda: (time.perf_counter() - t0_wall, time.process_time() - t0_cpu)

def file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024**2)

def write_json(df: pl.DataFrame, path: Path):
    # Медленно и тяжело — но нужен для сравнения
    with path.open("w", encoding="utf-8") as f:
        json.dump(df.to_dicts(), f, ensure_ascii=False)

def write_jsonl(df: pl.DataFrame, path: Path):
    df.write_ndjson(path)

def write_csv(df: pl.DataFrame, path: Path):
    df.write_csv(path)

def write_parquet(df: pl.DataFrame, path: Path):
    df.write_parquet(path, compression="zstd")

def write_orc(df: pl.DataFrame, path: Path):

    table = df.to_arrow()
    with path.open("wb") as f:
        orc.write_table(table, f)

def write_sqlite(df: pl.DataFrame, path: Path, batch_size: int = 50_000):
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    cur = conn.cursor()

    # 1) создаём таблицу
    cur.execute("""
        CREATE TABLE comments (
            id TEXT,
            author TEXT,
            subreddit TEXT,
            body TEXT,
            created_utc INTEGER,
            score INTEGER,
            controversiality INTEGER
        )
    """)

    cols = ["id", "author", "subreddit", "body", "created_utc", "score", "controversiality"]
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO comments ({','.join(cols)}) VALUES ({placeholders})"

    # 2) вставляем батчами из Polars
    n = df.height
    for start in range(0, n, batch_size):
        chunk = df.slice(start, batch_size).select(cols)
        rows = chunk.rows()  # list[tuple], но только для маленького куска
        cur.executemany(sql, rows)
        conn.commit()

    # 3) индексы (по желанию, но полезно для чтения)
    cur.execute("CREATE INDEX idx_subreddit ON comments(subreddit)")
    cur.execute("CREATE INDEX idx_created_utc ON comments(created_utc)")
    conn.commit()
    conn.close()

def main():
    print("Loading JSONL...")
    df = pl.read_ndjson(RAW_PATH)

    # Оставляем только нужные поля + приводим типы
    df = df.select([
        pl.col("id").cast(pl.Utf8),
        pl.col("author").cast(pl.Utf8),
        pl.col("subreddit").cast(pl.Utf8),
        pl.col("body").cast(pl.Utf8),
        pl.col("created_utc").cast(pl.Int64),
        pl.col("score").cast(pl.Int32),
        pl.col("controversiality").cast(pl.Int8),
    ])

    benchmarks = [
        # ("json", OUT_DIR / "comments.json", write_json),
        ("jsonl", OUT_DIR / "comments.jsonl", write_jsonl),
        ("csv", OUT_DIR / "comments.csv", write_csv),
        ("parquet", OUT_DIR / "comments.parquet", write_parquet),
        ("orc", OUT_DIR / "comments.orc", write_orc),
        ("sqlite", OUT_DIR / "comments.sqlite", write_sqlite),
    ]

    rows = []
    for fmt, path, fn in benchmarks:
        if path.exists():
            path.unlink()
        print(f"Writing {fmt} -> {path}")
        with timer() as elapsed:
            fn(df, path)
        wall, cpu = elapsed()
        size_mb = file_size_mb(path)
        rows.append((fmt, wall, cpu, size_mb))
        print(f"{fmt}: wall={wall:.2f}s cpu={cpu:.2f}s size={size_mb:.1f}MB")

    # сохранить результаты
    with RESULTS_CSV.open("w", encoding="utf-8") as f:
        f.write("format,wall_time_sec,cpu_time_sec,file_size_mb\n")
        for fmt, wall, cpu, size in rows:
            f.write(f"{fmt},{wall:.6f},{cpu:.6f},{size:.3f}\n")

if __name__ == "__main__":
    main()
