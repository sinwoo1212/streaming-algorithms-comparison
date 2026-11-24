from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import random
import statistics
import sys
import time
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator


MASK64 = (1 << 64) - 1


def splitmix64(x: int) -> int:
    """Stable 64-bit mixing function used to derive independent hash values."""
    x = (x + 0x9E3779B97F4A7C15) & MASK64
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9 & MASK64
    x = (x ^ (x >> 27)) * 0x94D049BB133111EB & MASK64
    return (x ^ (x >> 31)) & MASK64


def stream_ratings(path: Path) -> Iterator[tuple[int, int, int, int]]:
    with path.open("r", encoding="latin-1") as source:
        for line in source:
            user_id, movie_id, rating, timestamp = line.rstrip().split("::")
            yield int(user_id), int(movie_id), int(rating), int(timestamp)


def pair_key(user_id: int, movie_id: int) -> int:
    return (user_id << 32) | movie_id


class BloomFilter:
    def __init__(self, bit_count: int, hash_count: int) -> None:
        self.bit_count = bit_count
        self.hash_count = hash_count
        self.bits = bytearray((bit_count + 7) // 8)

    def _positions(self, item: int) -> Iterable[int]:
        h1 = splitmix64(item ^ 0x243F6A8885A308D3)
        h2 = splitmix64(item ^ 0x13198A2E03707344) | 1
        for i in range(self.hash_count):
            yield (h1 + i * h2) % self.bit_count

    def add(self, item: int) -> None:
        for position in self._positions(item):
            self.bits[position >> 3] |= 1 << (position & 7)

    def __contains__(self, item: int) -> bool:
        return all(
            self.bits[position >> 3] & (1 << (position & 7))
            for position in self._positions(item)
        )

    @property
    def structure_bytes(self) -> int:
        return len(self.bits)


class CountMinSketch:
    def __init__(self, width: int, depth: int) -> None:
        self.width = width
        self.depth = depth
        self.tables = [array("I", [0]) * width for _ in range(depth)]
        self.seeds = [splitmix64(0xA4093822299F31D0 + i) for i in range(depth)]

    def _position(self, item: int, row: int) -> int:
        return splitmix64(item ^ self.seeds[row]) % self.width

    def add(self, item: int, count: int = 1) -> None:
        for row, table in enumerate(self.tables):
            table[self._position(item, row)] += count

    def estimate(self, item: int) -> int:
        return min(
            table[self._position(item, row)]
            for row, table in enumerate(self.tables)
        )

    @property
    def structure_bytes(self) -> int:
        return sum(table.buffer_info()[1] * table.itemsize for table in self.tables)


def deep_size_set(values: set[int]) -> int:
    return sys.getsizeof(values) + sum(sys.getsizeof(value) for value in values)


def deep_size_dict(values: dict[int, int]) -> int:
    return sys.getsizeof(values) + sum(
        sys.getsizeof(key) + sys.getsizeof(value) for key, value in values.items()
    )


@dataclass
class BloomResult:
    bits_per_item: int
    bit_count: int
    hash_count: int
    structure_bytes: int
    build_seconds: float
    build_throughput: float
    query_seconds: float
    false_positives: int
    negative_queries: int
    false_positive_rate: float
    theoretical_fpr: float
    false_negatives: int


@dataclass
class CMSResult:
    width: int
    depth: int
    structure_bytes: int
    build_seconds: float
    build_throughput: float
    query_seconds: float
    mean_absolute_error: float
    mean_relative_error: float
    median_relative_error: float
    max_absolute_error: int
    exact_match_rate: float
    never_underestimated: bool


def collect_ground_truth(path: Path) -> tuple[set[int], dict[int, int], dict[str, int], float]:
    pairs: set[int] = set()
    movie_counts: dict[int, int] = {}
    min_timestamp = 2**63 - 1
    max_timestamp = 0
    max_user = 0
    max_movie = 0
    rating_count = 0
    start = time.perf_counter()
    for user_id, movie_id, _rating, timestamp in stream_ratings(path):
        pairs.add(pair_key(user_id, movie_id))
        movie_counts[movie_id] = movie_counts.get(movie_id, 0) + 1
        min_timestamp = min(min_timestamp, timestamp)
        max_timestamp = max(max_timestamp, timestamp)
        max_user = max(max_user, user_id)
        max_movie = max(max_movie, movie_id)
        rating_count += 1
    elapsed = time.perf_counter() - start
    metadata = {
        "rating_count": rating_count,
        "unique_pairs": len(pairs),
        "unique_movies": len(movie_counts),
        "max_user_id": max_user,
        "max_movie_id": max_movie,
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }
    return pairs, movie_counts, metadata, elapsed


def generate_negative_queries(
    truth: set[int], max_user: int, max_movie: int, count: int, seed: int
) -> list[int]:
    rng = random.Random(seed)
    negatives: set[int] = set()
    while len(negatives) < count:
        candidate = pair_key(rng.randint(1, max_user), rng.randint(1, max_movie))
        if candidate not in truth:
            negatives.add(candidate)
    return list(negatives)


def run_bloom(
    path: Path,
    truth: set[int],
    metadata: dict[str, int],
    negative_queries: list[int],
    bits_per_item_values: list[int],
) -> list[BloomResult]:
    results: list[BloomResult] = []
    positive_queries = random.Random(20261124).sample(
        list(truth), min(50_000, len(truth))
    )
    n = metadata["unique_pairs"]
    for bits_per_item in bits_per_item_values:
        bit_count = n * bits_per_item
        hash_count = max(1, round(bits_per_item * math.log(2)))
        bloom = BloomFilter(bit_count, hash_count)
        start = time.perf_counter()
        for user_id, movie_id, _rating, _timestamp in stream_ratings(path):
            bloom.add(pair_key(user_id, movie_id))
        build_seconds = time.perf_counter() - start

        start = time.perf_counter()
        false_positives = sum(key in bloom for key in negative_queries)
        false_negatives = sum(key not in bloom for key in positive_queries)
        query_seconds = time.perf_counter() - start
        theoretical_fpr = (1 - math.exp(-hash_count * n / bit_count)) ** hash_count
        results.append(
            BloomResult(
                bits_per_item=bits_per_item,
                bit_count=bit_count,
                hash_count=hash_count,
                structure_bytes=bloom.structure_bytes,
                build_seconds=build_seconds,
                build_throughput=metadata["rating_count"] / build_seconds,
                query_seconds=query_seconds,
                false_positives=false_positives,
                negative_queries=len(negative_queries),
                false_positive_rate=false_positives / len(negative_queries),
                theoretical_fpr=theoretical_fpr,
                false_negatives=false_negatives,
            )
        )
    return results


def run_cms(
    path: Path,
    movie_counts: dict[int, int],
    metadata: dict[str, int],
    widths: list[int],
    depth: int,
) -> list[CMSResult]:
    results: list[CMSResult] = []
    for width in widths:
        cms = CountMinSketch(width, depth)
        start = time.perf_counter()
        for _user_id, movie_id, _rating, _timestamp in stream_ratings(path):
            cms.add(movie_id)
        build_seconds = time.perf_counter() - start

        start = time.perf_counter()
        estimates = {movie_id: cms.estimate(movie_id) for movie_id in movie_counts}
        query_seconds = time.perf_counter() - start
        absolute_errors = [estimates[key] - count for key, count in movie_counts.items()]
        relative_errors = [
            (estimates[key] - count) / count for key, count in movie_counts.items()
        ]
        results.append(
            CMSResult(
                width=width,
                depth=depth,
                structure_bytes=cms.structure_bytes,
                build_seconds=build_seconds,
                build_throughput=metadata["rating_count"] / build_seconds,
                query_seconds=query_seconds,
                mean_absolute_error=statistics.fmean(absolute_errors),
                mean_relative_error=statistics.fmean(relative_errors),
                median_relative_error=statistics.median(relative_errors),
                max_absolute_error=max(absolute_errors),
                exact_match_rate=sum(error == 0 for error in absolute_errors) / len(absolute_errors),
                never_underestimated=all(error >= 0 for error in absolute_errors),
            )
        )
    return results


def write_csv(path: Path, rows: list[object]) -> None:
    dictionaries = [asdict(row) for row in rows]
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=dictionaries[0].keys())
        writer.writeheader()
        writer.writerows(dictionaries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    pairs, movie_counts, metadata, truth_seconds = collect_ground_truth(args.ratings)
    negative_queries = generate_negative_queries(
        pairs,
        metadata["max_user_id"],
        metadata["max_movie_id"],
        count=100_000,
        seed=20261124,
    )
    bloom_results = run_bloom(
        args.ratings, pairs, metadata, negative_queries, [4, 8, 12, 16]
    )
    cms_results = run_cms(
        args.ratings, movie_counts, metadata, [512, 1024, 2048, 4096], depth=5
    )

    summary = {
        "dataset": metadata,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        },
        "ground_truth": {
            "build_seconds": truth_seconds,
            "pair_set_bytes": deep_size_set(pairs),
            "movie_count_dict_bytes": deep_size_dict(movie_counts),
        },
        "bloom": [asdict(row) for row in bloom_results],
        "count_min_sketch": [asdict(row) for row in cms_results],
    }
    (args.output / "results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(args.output / "bloom_results.csv", bloom_results)
    write_csv(args.output / "cms_results.csv", cms_results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
