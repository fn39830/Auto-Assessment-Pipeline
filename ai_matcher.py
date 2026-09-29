import os
import json
import requests
from dotenv import load_dotenv

# Loaded here, before API_KEY is read below — without this, API_KEY would
# be set at import time before .env's contents ever reach os.environ,
# silently resulting in a 401 on every request (this bit us for real once).
load_dotenv()

API_URL = "https://api.anthropic.com/v1/messages"
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-sonnet-4-6"

# Batch size of 15, scoped to one paper per batch: fewer requests means
# lower cost and faster processing than one call per question, and keeping
# batches paper-scoped means every question in a batch shares the same
# spec list, so the prompt doesn't need to juggle multiple subjects.
BATCH_SIZE = 15


def load_spec_list(spec_list_path, subject, exam_board):
    """
    Loads spec_list.json and filters it down to just the relevant
    subject/board, since that's all one paper's questions could map to.

    Args:
        spec_list_path (str): path to spec_list.json.
        subject (str): e.g. "Physics".
        exam_board (str): e.g. "OCR".

    Returns:
        list[dict]: matching spec point entries.
    """
    with open(spec_list_path, "r") as f:
        all_specs = json.load(f)

    return [
        s for s in all_specs
        if s["subject"] == subject and s["exam_board"] == exam_board
    ]


def build_prompt(question_batch, spec_points):
    """
    Builds the prompt text sent to Claude for one batch of questions.

    Args:
        question_batch (list[dict]): each dict has "id" and "text" keys.
        spec_points (list[dict]): relevant spec points for this paper's subject/board.

    Returns:
        str: the full prompt text.
    """
    spec_list_text = "\n".join(
        f"{s['tag']}: {s['description']}" for s in spec_points
    )

    # Each question is tagged with its own unique ID (e.g.
    # "Physics_OCR_2022_2_Q1") rather than relying on response array order.
    # Array-order matching breaks silently if the model skips or reorders
    # one entry — everything after it shifts and mismatches. An explicit
    # ID that the model echoes back removes that failure mode entirely,
    # since matching happens by ID lookup, not position.
    questions_text = "\n\n".join(
        f"ID: {q['id']}\nQuestion: {q['text']}" for q in question_batch
    )

    prompt = f"""You are classifying exam questions against specification points.

Here is the list of valid specification points for this subject:
{spec_list_text}

For each question, search the full specification list carefully and pick
the single spec point whose description most precisely matches the exact
physics concept being tested — not just the general topic area. Read every
question's specific wording (numbers, named quantities, named effects)
before deciding, rather than defaulting to the first plausible-looking tag.
Only use "UNKNOWN" if genuinely no spec point relates to the question at all.

{questions_text}

Respond with ONLY a valid JSON array, no other text, no markdown formatting,
no explanation or reasoning before or after the array.
Each entry must have exactly this shape:
{{"id": "<the question's ID>", "spec_code": "<matching tag>"}}
"""
    return prompt


def call_claude_api(prompt):
    """
    Sends a single request to the Claude API and returns the raw text response.

    Uses raw requests rather than the official anthropic SDK — a deliberate
    choice to practice building headers/payloads directly. Worth swapping
    to the SDK before this becomes a "finished" portfolio piece, since it
    handles retries and rate limiting automatically, which this only does
    partially right now.

    Args:
        prompt (str): the full prompt to send.

    Returns:
        str or None: the model's raw text response, or None if the call failed.
    """
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    payload = {
        "model": MODEL,
        "max_tokens": 2000,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return None

    data = response.json()
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError) as e:
        print(f"Unexpected API response shape: {e}")
        return None
    


def parse_classification_response(raw_text):
    """
    Parses Claude's raw text response into a list of classification dicts.

    Args:
        raw_text (str): the model's raw text response.

    Returns:
        list[dict] or None: parsed entries, or None if parsing failed entirely.
    """
    if raw_text is None:
        return None

    cleaned = raw_text.strip()
    # Models occasionally wrap JSON in markdown fences even when told not
    # to, so this strips them defensively rather than assuming a clean
    # response every time.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Could not parse JSON response: {e}")
        return None


def classify_batch(question_batch, spec_points):
    """
    Classifies one batch of questions (up to BATCH_SIZE) via a single API call.
    Isolates and retries any question IDs missing from the response, once,
    in a separate smaller request — rather than discarding the whole batch.

    Args:
        question_batch (list[dict]): each dict has "id" and "text" keys.
        spec_points (list[dict]): relevant spec points for this batch's paper.

    Returns:
        list[dict]: classification results, id + spec_code, for every question
                    that could be successfully classified. Questions that fail
                    even after retry are given spec_code "FAILED".
    """
    prompt = build_prompt(question_batch, spec_points)
    raw_response = call_claude_api(prompt)
    results = parse_classification_response(raw_response)

    if results is None:
        results = []

    # Work out which question IDs are missing from the response
    returned_ids = {r.get("id") for r in results if isinstance(r, dict)}
    sent_ids = {q["id"] for q in question_batch}
    missing_ids = sent_ids - returned_ids

    # If 14 of 15 questions classify fine and one comes back malformed or
    # missing, discarding all 15 would waste the 14 good results. Isolating
    # just the failed ID(s) into a smaller follow-up request recovers the
    # good data and gives the model one more chance before giving up on it.
    if missing_ids:
        print(f"Retrying {len(missing_ids)} missing question(s): {missing_ids}")
        missing_batch = [q for q in question_batch if q["id"] in missing_ids]
        retry_prompt = build_prompt(missing_batch, spec_points)
        retry_raw = call_claude_api(retry_prompt)
        retry_results = parse_classification_response(retry_raw)

        if retry_results:
            results.extend(retry_results)
            returned_ids.update(r.get("id") for r in retry_results if isinstance(r, dict))

        # Anything still missing after the retry gets marked as failed,
        # rather than silently disappearing from the output
        still_missing = sent_ids - returned_ids
        for qid in still_missing:
            results.append({"id": qid, "spec_code": "FAILED"})

    return results


def classify_paper(questions, subject, exam_board, spec_list_path="spec_list.json"):
    """
    Classifies all questions for a single paper, batching them in groups
    of BATCH_SIZE, scoped to this one paper's subject/board.

    Args:
        questions (list[dict]): each dict has "id" and "text" keys, covering
                                every question extracted from this paper.
        subject (str): e.g. "Physics".
        exam_board (str): e.g. "OCR".
        spec_list_path (str): path to spec_list.json.

    Returns:
        list[dict]: classification results for every question in the paper.
    """
    spec_points = load_spec_list(spec_list_path, subject, exam_board)
    if not spec_points:
        print(f"No spec points found for {subject} {exam_board} — check spec_list.json")
        return []

    all_results = []
    for i in range(0, len(questions), BATCH_SIZE):
        batch = questions[i:i + BATCH_SIZE]
        batch_results = classify_batch(batch, spec_points)
        all_results.extend(batch_results)

    return all_results


if __name__ == "__main__":
    if not API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Set it before running this script."
        )

    # Example usage — replace with real extracted question data
    example_questions = [
        {"id": "Physics_OCR_2022_2_Q1", "text": "Calculate the length BC. [2]"},
        {"id": "Physics_OCR_2022_2_Q2", "text": "State the meaning of periodicity. [1]"},
    ]

    results = classify_paper(example_questions, subject="Physics", exam_board="OCR")
    print(json.dumps(results, indent=2))