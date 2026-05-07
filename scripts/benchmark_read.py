import argparse
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pyarrow.orc as pa_orc

RAW_PATH = Path("data/raw/reddit_10gb.jsonl")
DATA_DIR = Path("data/converted")
RESULTS_CSV = Path("results/read_benchmark.csv")
RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)

CPP_BINDINGS_DIR = Path("cpp_bindings")
sys.path.append(CPP_BINDINGS_DIR.as_posix())

FILES = {
    "jsonl": DATA_DIR / "comments.jsonl",
    "csv": DATA_DIR / "comments.csv",
    "parquet": DATA_DIR / "comments.parquet",
    "orc": DATA_DIR / "comments.orc",
    "sqlite": DATA_DIR / "comments.sqlite",
}


@contextmanager
def timer():
    t0_wall = time.perf_counter()
    t0_cpu = time.process_time()
    yield lambda: (time.perf_counter() - t0_wall, time.process_time() - t0_cpu)


def run_query(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchall()


def load_extensions(con: duckdb.DuckDBPyConnection):
    for ext in ("json", "sqlite"):
        try:
            con.execute(f"INSTALL {ext};")
        except Exception:
            pass
        try:
            con.execute(f"LOAD {ext};")
        except Exception:
            pass


def source_from_format(con: duckdb.DuckDBPyConnection, fmt: str, path: Path) -> str:
    p = path.as_posix()
    if fmt == "jsonl":
        return f"read_json_auto('{p}', format='newline_delimited')"
    if fmt == "csv":
        return f"read_csv_auto('{p}')"
    if fmt == "parquet":
        return f"read_parquet('{p}')"
    if fmt == "orc":
        with path.open("rb") as f:
            orc_table = pa_orc.ORCFile(f).read()
        con.register("__ORC_ARROW__", orc_table)
        return "__ORC_ARROW__"
    if fmt == "sqlite":
        return f"sqlite_scan('{p}', 'comments')"
    raise ValueError(f"Unknown format: {fmt}")


def benchmark_queries(con: duckdb.DuckDBPyConnection, fmt: str, source_relation: str, mode: str):
    rows = []

    with timer() as elapsed:
        run_query(con, f"SELECT count(*) FROM {source_relation}")
    wall, cpu = elapsed()
    rows.append((mode, fmt, "read", wall, cpu))

    with timer() as elapsed:
        run_query(
            con,
            f"""
            SELECT count(*)
            FROM {source_relation}
            WHERE score > 10 AND subreddit IS NOT NULL
            """,
        )
    wall, cpu = elapsed()
    rows.append((mode, fmt, "filter", wall, cpu))

    with timer() as elapsed:
        run_query(
            con,
            f"""
            SELECT subreddit, count(*) AS cnt, avg(score) AS avg_score
            FROM {source_relation}
            WHERE subreddit IS NOT NULL
            GROUP BY subreddit
            ORDER BY cnt DESC
            LIMIT 100
            """,
        )
    wall, cpu = elapsed()
    rows.append((mode, fmt, "groupby", wall, cpu))

    with timer() as elapsed:
        run_query(
            con,
            f"""
            SELECT subreddit, author, created_utc, score
            FROM (
                SELECT
                    subreddit,
                    author,
                    created_utc,
                    score,
                    row_number() OVER (
                        PARTITION BY subreddit
                        ORDER BY created_utc DESC
                    ) AS rn
                FROM {source_relation}
                WHERE subreddit IS NOT NULL AND created_utc IS NOT NULL
            ) t
            WHERE rn <= 3
            """,
        )
    wall, cpu = elapsed()
    rows.append((mode, fmt, "window", wall, cpu))

    return rows


def bench_direct(fmt: str, path: Path):
    con = duckdb.connect(database=":memory:")
    load_extensions(con)
    source_relation = source_from_format(con, fmt, path)
    rows = benchmark_queries(con, fmt, source_relation, mode="direct")
    if fmt == "orc":
        con.unregister("__ORC_ARROW__")
    con.close()
    return rows


def bench_materialized(fmt: str, path: Path):
    con = duckdb.connect(database=":memory:")
    load_extensions(con)
    source_relation = source_from_format(con, fmt, path)

    rows = []
    with timer() as elapsed:
        con.execute("DROP TABLE IF EXISTS comments")
        con.execute(f"CREATE TEMP TABLE comments AS SELECT * FROM {source_relation}")
    wall, cpu = elapsed()
    rows.append(("materialized", fmt, "materialize", wall, cpu))

    rows.extend(benchmark_queries(con, fmt, "comments", mode="materialized"))
    if fmt == "orc":
        con.unregister("__ORC_ARROW__")
    con.close()
    return rows


def bench_cpp_binding(path: Path):
    """Benchmark reading/counting raw JSONL rows through a C++ pybind11 extension."""
    if not path.exists():
        print(f"[WARN] skip cpp_binding, raw file not found: {path}")
        return []

    try:
        import fast_count
    except ImportError as e:
        print(f"[WARN] skip cpp_binding, extension is not built: {e}")
        print("[WARN] build it first:")
        print("       cd cpp_bindings")
        print("       python setup.py build_ext --inplace")
        print("       cd ..")
        return []

    print("Benchmarking cpp_binding (direct)...")
    with timer() as elapsed:
        fast_count.count_lines(path.as_posix())
    wall, cpu = elapsed()

    return [("direct", "cpp_binding", "read", wall, cpu)]


def parse_args():
    parser = argparse.ArgumentParser(description="Read benchmark for data formats.")
    parser.add_argument(
        "--mode",
        choices=("direct", "materialized", "both"),
        default="both",
        help="Benchmark mode.",
    )
    parser.add_argument(
        "--results",
        default=RESULTS_CSV.as_posix(),
        help="Output CSV path.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    results_csv = Path(args.results)
    results_csv.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for fmt in ("jsonl", "csv", "parquet", "orc", "sqlite"):
        path = FILES[fmt]
        if not path.exists():
            print(f"[WARN] skip {fmt}, file not found: {path}")
            continue

        print(f"Benchmarking {fmt} ({args.mode})...")
        try:
            if args.mode in ("direct", "both"):
                all_rows.extend(bench_direct(fmt, path))
            if args.mode in ("materialized", "both"):
                all_rows.extend(bench_materialized(fmt, path))
        except Exception as e:
            print(f"[ERROR] {fmt} failed: {e}")

    if args.mode in ("direct", "both"):
        all_rows.extend(bench_cpp_binding(RAW_PATH))

    with results_csv.open("w", encoding="utf-8") as f:
        f.write("mode,format,query_type,wall_time_sec,cpu_time_sec\n")
        for mode, fmt, qtype, wall, cpu in all_rows:
            f.write(f"{mode},{fmt},{qtype},{wall:.6f},{cpu:.6f}\n")

    print(f"Done: {results_csv}")


if __name__ == "__main__":
    main()