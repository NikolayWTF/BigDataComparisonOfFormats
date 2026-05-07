import argparse
import json
import random
import string
from pathlib import Path

RAW_PATH = Path("data/raw/reddit_10gb.jsonl")

SUBREDDITS = [
    "MachineLearning",
    "datascience",
    "Python",
    "bigdata",
    "AskReddit",
    "programming",
    "learnpython",
    "statistics",
]

AUTHORS = [f"user_{i}" for i in range(1, 501)]


def random_text(min_words: int = 5, max_words: int = 25) -> str:
    n_words = random.randint(min_words, max_words)
    words = []
    for _ in range(n_words):
        word_len = random.randint(3, 10)
        words.append("".join(random.choices(string.ascii_lowercase, k=word_len)))
    return " ".join(words)


def generate_jsonl(path: Path, rows: int, seed: int) -> None:
    random.seed(seed)
    path.parent.mkdir(parents=True, exist_ok=True)

    start_ts = 1_609_459_200  # 2021-01-01

    with path.open("w", encoding="utf-8") as f:
        for i in range(rows):
            item = {
                "id": f"synthetic_{i}",
                "author": random.choice(AUTHORS),
                "subreddit": random.choice(SUBREDDITS),
                "body": random_text(),
                "created_utc": start_ts + random.randint(0, 365 * 24 * 3600),
                "score": random.randint(-20, 500),
                "controversiality": random.randint(0, 1),
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate small synthetic reddit-like JSONL for HW1 benchmarks."
    )
    parser.add_argument("--rows", type=int, default=200_000, help="Number of synthetic rows.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--output",
        default=RAW_PATH.as_posix(),
        help="Output JSONL path. Default: data/raw/reddit_10gb.jsonl",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output = Path(args.output)
    generate_jsonl(output, rows=args.rows, seed=args.seed)
    size_mb = output.stat().st_size / (1024**2)
    print(f"Generated {args.rows:,} rows -> {output} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
