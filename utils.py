import gzip
from concurrent.futures import ThreadPoolExecutor


def parse_bed_file(filepath):
    """
    Parse a BED or BED.GZ file into a sorted list of intervals and compute total covered length.
    Returns:
        intervals: List of tuples (chrom, start, end)
        total_length: Sum of all interval lengths
    """
    intervals = []
    open_func = gzip.open if filepath.endswith('.gz') else open

    with open_func(filepath, 'rt', encoding='utf-8', errors='ignore') as file:
        for line in file:
            if line.startswith(('#', 'track', 'browser')) or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) < 3:
                continue
            try:
                chrom = parts[0]
                start = int(parts[1])
                end = int(parts[2])
                if end >= start:
                    intervals.append((chrom, start, end))
            except ValueError:
                continue

    intervals.sort(key=lambda x: (x[0], x[1]))
    total_length = sum(end - start for _, start, end in intervals)
    return intervals, total_length


def calculate_overlap(a_intervals, a_len, b_intervals, b_len):
    """
    Calculate the Jaccard index between two sets of intervals.
    """
    overlap = 0
    i = j = 0

    while i < len(a_intervals) and j < len(b_intervals):
        a_chrom, a_start, a_end = a_intervals[i]
        b_chrom, b_start, b_end = b_intervals[j]

        if a_chrom < b_chrom:
            i += 1
        elif a_chrom > b_chrom:
            j += 1
        else:
            start = max(a_start, b_start)
            end = min(a_end, b_end)
            if start < end:
                overlap += end - start

            if a_end < b_end:
                i += 1
            else:
                j += 1

    union = a_len + b_len - overlap
    return overlap / union if union > 0 else 0.0


def compute_all_jaccards(input_tree, input_len, db_files):
    """
    Compute Jaccard indices between input file and all files in db_files in parallel.
    Each db_file should have keys: 'filename', 'intervals', 'total_length'
    """
    def task(db_file):
        jaccard = calculate_overlap(
            input_tree, input_len,
            parse_bed_file(db_file.filepath)[0],
            db_file.total_length
        )
        return {
            'filename': db_file.filename,
            'jaccard': round(jaccard, 4)
        }

    with ThreadPoolExecutor() as executor:
        results = list(executor.map(task, db_files))

    return sorted(results, key=lambda x: x['jaccard'], reverse=True)
