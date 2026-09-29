import base64
import json
import requests
from ai_matcher import API_URL, API_KEY, ANTHROPIC_VERSION, MODEL, call_claude_api


def encode_image(image_path):
    """
    Reads an image file and base64-encodes it, the format the Claude API
    requires for image content blocks (JSON can't hold raw binary data,
    so the bytes get converted to a text-safe encoding first).

    Args:
        image_path (str): path to the photographed answer (jpg/png/etc).

    Returns:
        tuple[str, str]: (base64-encoded image data, media type string).
    """
    extension = image_path.rsplit(".", 1)[-1].lower()
    media_type_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    media_type = media_type_map.get(extension, "image/jpeg")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    encoded_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    return encoded_data, media_type


def build_marking_prompt(question_text, mark_scheme_text, max_marks):
    """
    Builds the text portion of the marking prompt. The student's answer
    itself isn't text here — it arrives as the image content block built
    separately in mark_answer(), since Claude reads it directly rather
    than needing it pre-transcribed.

    Args:
        question_text (str): the question being answered.
        mark_scheme_text (str): raw extracted text of the paper's full
                                mark scheme — not pre-parsed into a
                                structured lookup (see design note: mark
                                schemes are too inconsistently formatted
                                for a reliable offline parser, so Claude
                                is given the raw text and locates the
                                relevant marking points itself).
        max_marks (int): total marks available for this question.

    Returns:
        str: the prompt text.
    """
    prompt = f"""You are marking a student's handwritten or typed answer to an exam question, shown in the attached image.

Question:
{question_text}

This question is worth {max_marks} marks in total.

Here is the full mark scheme for this paper. Find the marking points that
apply to this specific question and use them to mark the answer:
{mark_scheme_text}

Read the answer in the image carefully, then award marks strictly according
to the mark scheme's marking points. Give brief feedback explaining what
was correct and what was missing or wrong.

Respond with ONLY valid JSON, no other text, no markdown formatting,
no explanation before or after. Use exactly this shape:
{{"marks_awarded": <integer>, "max_marks": {max_marks}, "feedback": "<brief explanation>"}}
"""
    return prompt


def call_claude_vision_api(prompt_text, image_path):
    """
    Sends a request containing both an image and text to the Claude API.

    Structurally different from ai_matcher.call_claude_api(), which only
    ever sends a plain string as "content". Here "content" is a LIST of
    blocks — an image block and a text block together — since a single
    message can mix modalities. Image block goes first: Claude's vision
    guide recommends image-before-text ordering for best results.

    Args:
        prompt_text (str): the text portion of the prompt.
        image_path (str): path to the image to send.

    Returns:
        str or None: the model's raw text response, or None if the call failed.
    """
    image_data, media_type = encode_image(image_path)

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    payload = {
        "model": MODEL,
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Vision API request failed: {e}")
        return None

    data = response.json()
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError) as e:
        print(f"Unexpected API response shape: {e}")
        return None


def parse_marking_response(raw_text):
    """
    Parses Claude's raw marking response into a dict. Same extraction
    approach as ai_matcher's classification parser — finds the JSON object
    between the first { and last }, rather than assuming a perfectly clean
    response, since the model can still add stray text around it.

    Args:
        raw_text (str): the model's raw text response.

    Returns:
        dict or None: {"marks_awarded", "max_marks", "feedback"}, or None
                    if parsing failed.
    """
    if raw_text is None:
        return None

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Could not parse marking response: {e}")
        return None


def mark_answer(question_text, mark_scheme_text, max_marks, image_path):
    """
    Marks a photographed student answer against a mark scheme.

    Args:
        question_text (str): the question being answered.
        mark_scheme_text (str): raw text of the paper's full mark scheme.
        max_marks (int): total marks available for this question.
        image_path (str): path to the photographed answer.

    Returns:
        dict or None: {"marks_awarded", "max_marks", "feedback"}, or None
                    if marking failed (network error or unparseable response).
    """
    prompt = build_marking_prompt(question_text, mark_scheme_text, max_marks)
    raw_response = call_claude_vision_api(prompt, image_path)
    return parse_marking_response(raw_response)


def build_shadow_question_prompt(question_text, question_mark_scheme, feedback, spec_description):
    """
    Builds the prompt for generating a follow-up practice question, used
    when a student scored below full marks.

    Diagnoses WHY marks were lost from the marking feedback, distinguishing
    two failure modes, and shapes the new question differently depending
    on which applies:
      - Structural/exam-technique gap (e.g. rambling prose instead of a
        clear structured answer, poor organisation) -> new question tests
        the same kind of structured-response skill, doesn't need to be the
        same specific spec point, just a similarly-shaped question.
      - Conceptual/knowledge gap (e.g. missing definitions, can't link
        ideas together) -> new question stays tightly scoped to the exact
        same spec point, phrased to directly probe the missing knowledge.

    Both cases return the same output shape (a new question + its own mark
    scheme) rather than diverging into different formats — kept simple
    deliberately, since a second differently-shaped output (e.g. a
    multiple-choice quiz) would cost more prompt/parsing/frontend time than
    it was worth given the project deadline.

    Only this question's specific mark scheme entry is passed in, not the
    whole paper's mark scheme — the model is diagnosing and regenerating,
    not re-marking, so the full document isn't needed here.

    Args:
        question_text (str): the original question.
        question_mark_scheme (str): mark scheme text for just this question.
        feedback (str): the feedback string from mark_answer().
        spec_description (str): the spec point description this question
                                was classified against (from bridge.py).

    Returns:
        str: the prompt text.
    """
    prompt = f"""A student answered this exam question and lost marks. Your job is to generate a new practice question to help them improve.

Original question:
{question_text}

Mark scheme for the original question:
{question_mark_scheme}

Feedback from marking the student's answer:
{feedback}

This question relates to the specification point: {spec_description}

First, diagnose why marks were lost, based on the feedback:
- STRUCTURAL gap: the student understood the content but expressed it
  poorly — e.g. unstructured prose instead of clear steps, rambling,
  disorganised answer for a question that needed a structured response.
- CONCEPTUAL gap: the student is missing actual knowledge — e.g. incorrect
  or missing definitions, can't explain a concept, can't link ideas
  together correctly.

If it's a STRUCTURAL gap: write a new question that requires a similarly
structured response (e.g. also needs a step-by-step or multi-part answer),
but it does not need to test the exact same spec point — pick a related
topic within the same general subject area.

If it's a CONCEPTUAL gap: write a new question that stays tightly focused
on the same specification point above, directly testing the specific
knowledge the student was missing.

Write an appropriate mark scheme for your new question, in the same style
as the mark scheme shown above.

Respond with ONLY valid JSON, no other text, no markdown formatting,
no explanation before or after. Use exactly this shape:
{{"new_question": "<the new question text, including a mark allocation like [X]>", "new_mark_scheme": "<the mark scheme for the new question>"}}
"""
    return prompt


def generate_shadow_question(question_text, question_mark_scheme, feedback, spec_description):
    """
    Generates a new practice question when a student scored below full
    marks, diagnosing the cause from the marking feedback first.

    Reuses ai_matcher.call_claude_api() and its response-parsing pattern
    directly — this is a text-only call (no image involved), unlike
    mark_answer(), so there's no need for the vision-specific request
    structure here.

    Args:
        question_text (str): the original question.
        question_mark_scheme (str): mark scheme text for just this question.
        feedback (str): the feedback string from mark_answer().
        spec_description (str): the spec point description this question
                                was classified against.

    Returns:
        dict or None: {"new_question", "new_mark_scheme"}, or None if
                    generation failed.
    """
    prompt = build_shadow_question_prompt(
        question_text, question_mark_scheme, feedback, spec_description
    )
    raw_response = call_claude_api(prompt)
    return parse_marking_response(raw_response)