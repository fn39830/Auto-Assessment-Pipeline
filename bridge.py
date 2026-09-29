import json
import spec_engine


def build_spec_index(spec_list_path="spec_list.json"):
    """
    Loads spec_list.json and builds a spec_engine.SpecIndex populated with
    every spec point in it. This is the C++ side of the pipeline, built
    once and reused for every search rather than rebuilt per question.

    Args:
        spec_list_path (str): path to spec_list.json.

    Returns:
        spec_engine.SpecIndex: populated index, ready for .search() calls.
    """
    with open(spec_list_path, "r") as f:
        all_specs = json.load(f)

    index = spec_engine.SpecIndex()
    for entry in all_specs:
        point = spec_engine.SpecPoint(
            entry["tag"],
            entry["description"],
            entry["subject"],
            entry["exam_board"],
        )
        index.addPoint(point)

    return index


def enrich_classifications(classification_results, index):
    """
    Takes ai_matcher.classify_paper()'s output (question id + spec_code
    pairs) and looks each spec_code up in the C++ engine, attaching the
    full SpecPoint details (description, subject, exam_board) rather than
    just the bare code.

    Runs entirely in memory — this is an intermediate pipeline step, not
    something that needs to persist to disk, so nothing is saved here.

    Any spec_code that doesn't exist in the index (e.g. Claude returned
    "UNKNOWN", or hallucinated a code not in spec_list.json) triggers a
    RuntimeError from SpecIndex.search(). Rather than letting that crash
    the whole batch or silently dropping the question, it's logged and
    kept in the output with spec_details set to None — so a failed lookup
    stays visible instead of quietly vanishing from the results.

    Args:
        classification_results (list[dict]): output of ai_matcher.classify_paper(),
                                              each entry has "id" and "spec_code".
        index (spec_engine.SpecIndex): built by build_spec_index().

    Returns:
        list[dict]: each entry has "id", "spec_code", and "spec_details"
                    (a dict of tag/description/subject/exam_board, or None
                    if the lookup failed).
    """
    enriched = []

    for result in classification_results:
        question_id = result.get("id")
        spec_code = result.get("spec_code")

        try:
            spec_point = index.search(spec_code)
            spec_details = {
                "tag": spec_point.tag,
                "description": spec_point.description,
                "subject": spec_point.subject,
                "exam_board": spec_point.exam_board,
            }
        except RuntimeError as e:
            print(f"Spec lookup failed for {question_id} (code '{spec_code}'): {e}")
            spec_details = None

        enriched.append({
            "id": question_id,
            "spec_code": spec_code,
            "spec_details": spec_details,
        })

    return enriched


if __name__ == "__main__":
    # Example usage — replace classification_results with real output from
    # ai_matcher.classify_paper() once spec_list.json is filled in
    example_classifications = [
        {"id": "Physics_OCR_2022_2_Q1", "spec_code": "1.1.1a"},
        {"id": "Physics_OCR_2022_2_Q2", "spec_code": "9.9.9z"},  # deliberately invalid, to test logging
    ]

    index = build_spec_index()
    results = enrich_classifications(example_classifications, index)

    for r in results:
        print(r)