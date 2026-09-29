import json
from extractor import extract_text_from_pdf
from extractor import clean_text
from question_splitter import split_into_questions_llm
from question_splitter import assign_question_ids
from ai_matcher import classify_paper
from bridge import build_spec_index
from bridge import enrich_classifications

def main():

    with open("catalog.json", "r") as paper_file:
        catalog = json.load(paper_file)
        # Built once, outside the paper loop — the spec list doesn't change
        # between papers, so rebuilding this per paper would be wasted work.
        index = build_spec_index()

        for paper in catalog:
            # A plain list here, not a dict — questions get collected in
            # order across every page of this paper, and .extend() needs
            # a list on both sides (dicts don't support .extend() at all).
            all_raw_questions = []
            file_path = f"past_papers/{paper['subject']}_{paper['exam_board']}_{paper['year']}_{paper['paper_number']}.pdf"
            pages = extract_text_from_pdf(file_path)

            for page in pages:
                cleaned_page_text = clean_text(page, paper['exam_board'])
                questions = split_into_questions_llm(cleaned_page_text)  # was: split_into_questions(cleaned_page_text)
                # .extend(), not .append() — questions is itself a list, so
                # .append() would nest a whole list inside all_raw_questions
                # for every page, instead of merging all the individual
                # question strings into one flat list (same bug we hit and
                # fixed once already, earlier in this project).
                all_raw_questions.extend(questions)

            # Called ONCE per paper, after the page loop ends — not once
            # per page. assign_question_ids()'s internal counter resets to
            # 1 every time it's called, so calling it per page produced
            # colliding IDs (every page's first question became "Q1").
            # Calling it once, on the full collected list, lets the
            # numbering run continuously across the whole paper.
            all_question_IDs = assign_question_ids(
                all_raw_questions, paper['subject'], paper['exam_board'],
                paper['year'], paper['paper_number']
            )

            list_of_IDs = classify_paper(all_question_IDs, paper['subject'], paper['exam_board'])
            enriched = enrich_classifications(list_of_IDs, index)

            # enriched only carries id/spec_code/spec_details — it never
            # carries the question's own text or max_marks, since those
            # come from a completely different function (assign_question_ids).
            # Neither source alone has everything the marking flow will
            # later need by question ID, so both get combined below.

            # Step 1: turn all_question_IDs (a list) into a dict keyed by
            # id, so each question's text/max_marks can be looked up in
            # O(1) instead of scanning the list to find a matching id.
            raw_lookup = {}
            for q in all_question_IDs:
                print(q)
                raw_lookup[q["id"]] = {"text": q["text"], "max_marks": q["max_marks"]}

            # Step 2: loop through enriched once, using raw_lookup to pull
            # in the matching text/max_marks for each question, and combine
            # everything (text, max_marks, spec_code, description) into one
            # final entry per question.
            questions_data = {}
            for entry in enriched:
                if entry["spec_details"] is None:
                    continue  # spec lookup failed for this question — nothing to store
                the_id = entry["id"]
                matching_raw = raw_lookup[the_id]
                questions_data[the_id] = {
                    "text": matching_raw["text"],
                    "max_marks": matching_raw["max_marks"],
                    "spec_code": entry["spec_code"],
                    "description": entry["spec_details"]["description"],
                    }

            # Step 3: persist questions_data to disk, merged into whatever's
            # already saved there — so running main.py again for a
            # different paper doesn't wipe out previously saved questions,
            # and the same question later looked up by ID (e.g. by a
            # marking request from the frontend) survives between runs.
            try:
                with open("questions.json", "r") as question_file:
                    existing_data = json.load(question_file)
            except FileNotFoundError:
                # First run ever — nothing saved yet, start from empty
                # rather than crashing.
                existing_data = {}

            # Clear this paper's OWN old entries before merging fresh ones in —
            # question numbering isn't stable across runs, so stale entries from a
            # previous (possibly buggier) run must be removed, not left to linger.
            paper_prefix_for_cleanup = f"{paper['subject']}_{paper['exam_board']}_{paper['year']}_{paper['paper_number']}"
            existing_data = {
                key: value for key, value in existing_data.items()
                if not key.startswith(paper_prefix_for_cleanup)
}

            for key in questions_data:
                 existing_data[key] = questions_data[key]

            with open("questions.json", "w") as question_file:
                json.dump(existing_data, question_file, indent=2)

            print(enriched)


if __name__ == "__main__":
    main()