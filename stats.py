import json
import os

STATS_FILE = "student_stats.json"


def load_stats(stats_path=STATS_FILE):
    """
    Loads the running spec-point miss-count dict from disk.

    Deliberately simple — not a full spaced-repetition system. Just a
    running tally of how many times each spec point has been missed
    (marks_awarded < max_marks), enough to answer "which spec points does
    this student struggle with most" without building scheduling logic
    that wasn't achievable in the project timeline.

    Args:
        stats_path (str): path to the stats JSON file.

    Returns:
        dict: {spec_tag: miss_count}. Empty dict if the file doesn't exist yet.
    """
    if not os.path.exists(stats_path):
        return {}

    with open(stats_path, "r") as f:
        return json.load(f)


def save_stats(stats, stats_path=STATS_FILE):
    """
    Saves the stats dict back to disk.

    Args:
        stats (dict): {spec_tag: miss_count}.
        stats_path (str): path to the stats JSON file.
    """
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)


def record_result(spec_tag, marks_awarded, max_marks, stats_path=STATS_FILE):
    """
    Updates the running tally after one marked question. Only increments
    on an imperfect score — a spec point a student has always gotten full
    marks on shouldn't show up as a "weak spot" at all.

    Args:
        spec_tag (str): the spec point this question was classified against.
        marks_awarded (int): marks the student actually got.
        max_marks (int): marks available for the question.
        stats_path (str): path to the stats JSON file.

    Returns:
        dict: the updated stats dict.
    """
    stats = load_stats(stats_path)

    if marks_awarded < max_marks:
        stats[spec_tag] = stats.get(spec_tag, 0) + 1

    save_stats(stats, stats_path)
    return stats


def get_weakest_spec_points(top_n=5, stats_path=STATS_FILE):
    """
    Returns the spec points with the highest miss counts, most-missed first
    — the "top priority" list for what a student should be tested on next.

    Args:
        top_n (int): how many spec points to return.
        stats_path (str): path to the stats JSON file.

    Returns:
        list[tuple[str, int]]: (spec_tag, miss_count) pairs, sorted worst-first.
    """
    stats = load_stats(stats_path)
    sorted_stats = sorted(stats.items(), key=lambda item: item[1], reverse=True)
    return sorted_stats[:top_n]