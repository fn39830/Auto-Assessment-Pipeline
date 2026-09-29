import re
import json
from ai_matcher import call_claude_api
 
 
def extract_max_marks(question_text):
    """
    Pulls the mark allocation (e.g. the "[2]" or "[4]" printed at the end
    of a question) out of its text, needed so marking can score an answer
    out of a real number rather than an unknown total.
 
    Takes the LAST bracketed number found in the text specifically — a
    question can contain other bracketed numbers earlier (sub-part labels,
    references), but the final one is reliably the total mark allocation
    for that question on real exam papers.
 
    Args:
        question_text (str): one question's text, from split_into_questions().
 
    Returns:
        int or None: the mark allocation, or None if no bracketed number
                    was found (e.g. extraction/formatting was unusual).
    """
    matches = re.findall(r"\[(\d+)\]", question_text)
    if not matches:
        return None
    return int(matches[-1])
 
 
def count_real_words(text):
    """
    Counts substrings that look like actual words (3+ consecutive letters),
    as opposed to numbers, units, or symbols.
 
    Needed because the original length-only filter (MIN_QUESTION_LENGTH)
    let genuine non-question chunks through — e.g. a line of graph axis
    labels like "10 12 14 16 18 20 R/MΩ" is 22 characters long, easily
    clearing a length threshold, but contains zero real words. Real
    questions, even short ones, always contain multiple actual words;
    stray numeric data never does. Tested against real extraction failures
    before choosing this approach: the bad case scored 0 real words while
    every genuine question tested scored 10+, giving a wide, safe margin
    for the threshold.
 
    Args:
        text (str): any string to check.
 
    Returns:
        int: count of word-like substrings found.
    """
    return len(re.findall(r"[A-Za-z]{3,}", text))
 
 
def split_into_questions(cleaned_page_text):
    """
    Splits a page of cleaned exam text into individual questions.
 
    Looks for lines that start a new question, based on common numbering
    patterns seen across exam boards:
      - "1", "2", "3" at the start of a line (OCR/AQA main question numbers)
      - "0 1 . 2" style spaced sub-question numbers (OCR)
      - "(a)", "(b)" style sub-parts
 
    This exists because extract_text_from_pdf() and clean_text() only work
    at the page level — classification needs individual questions as
    separate units, so this is the missing link between the two.
 
    This is a heuristic, not a perfect parser — exam boards don't format
    question numbers identically, and pdfplumber occasionally mangles
    spacing on extraction, so some questions may split incorrectly.
    Good enough for feeding a classifier that can tolerate some noise;
    not something to rely on for exact mark-scheme accuracy.
 
    Args:
        cleaned_page_text (str): output of clean_text() for one page.
 
    Returns:
        list[str]: one string per detected question/sub-question.
    """
    question_start_pattern = re.compile(
        r"^(\d+(\s*\.\s*\d+)*|\(\s*[a-z]\s*\))"
    )
 
    lines = cleaned_page_text.split("\n")
 
    questions = []
    current_question_lines = []
 
    for line in lines:
        line = line.strip()
        if not line:
            continue
 
        if question_start_pattern.match(line):
            if current_question_lines:
                questions.append(" ".join(current_question_lines))
            current_question_lines = [line]
        else:
            if current_question_lines:
                current_question_lines.append(line)
 
    if current_question_lines:
        questions.append(" ".join(current_question_lines))
 
    # Two-part filter now, not just length. A chunk needs BOTH enough raw
    # length AND enough real words to count as a genuine question. Length
    # alone let numeric-only chunks (axis labels, data rows — plenty of
    # digits/symbols, few or no real words) slip through as if they were
    # real questions, which is what caused garbage entries to appear in
    # the app's question dropdown.
    MIN_QUESTION_LENGTH = 15
    MIN_REAL_WORDS = 4
    questions = [
        q for q in questions
        if len(q) >= MIN_QUESTION_LENGTH and count_real_words(q) >= MIN_REAL_WORDS
    ]
 
    return questions
 
 
def assign_question_ids(questions, subject, exam_board, year, paper_number):
    """
    Converts a list of plain question strings into the {"id", "text"} shape
    ai_matcher.py expects, giving each question a globally unique ID.
 
    Args:
        questions (list[str]): output of split_into_questions().
        subject (str): e.g. "Physics".
        exam_board (str): e.g. "OCR".
        year (str): e.g. "2022".
        paper_number (str): e.g. "2".
 
    Returns:
        list[dict]: each dict has "id", "text", and "max_marks" keys, ready
                    for ai_matcher.classify_paper() and the marking step.
    """
    id_prefix = f"{subject}_{exam_board}_{year}_{paper_number}"
 
    tagged_questions = []
    for i, question_text in enumerate(questions, start=1):
        tagged_questions.append({
            "id": f"{id_prefix}_Q{i}",
            "text": question_text,
            "max_marks": extract_max_marks(question_text),
        })
 
    return tagged_questions
 
 
def build_llm_split_prompt(page_text):
    """
    Builds the prompt asking Claude to extract clean, individual questions
    from a page of raw exam text.
 
    Exists because the regex-based split_into_questions() couldn't
    reliably distinguish real question starts from other numeric content
    on the page (graph axis labels, data table values, MCQ option lists) —
    all of which can start with a digit and pass a length/word-count
    filter without actually being a question. Letting the model read the
    page holistically, rather than pattern-matching line by line, avoids
    that whole class of false positive.
 
    Args:
        page_text (str): cleaned text of one page.
 
    Returns:
        str: the prompt text.
    """
    prompt = f"""Here is the text of one page from an exam paper:
 
{page_text}
 
Extract each individual exam question or sub-question from this page.
Ignore anything that is not a real question — this includes graph axis
labels, data table values, instructions, headers, page numbers, and
diagram captions. Each item you extract should be a complete, real
question or sub-question a student would actually answer, including its
mark allocation like [2] if one is shown.
 
If a question has no real content on this page (e.g. only a figure or
table with no actual question text), do not include it.
 
Respond with ONLY a valid JSON array of strings, no other text, no
markdown formatting, no explanation before or after. Each string is one
complete question's text. Example shape:
["1 A current is present in the circuit below... [1]", "16 (a) A graph of displacement... [2]"]
"""
    return prompt
 
 
def split_into_questions_llm(page_text):
    """
    LLM-based alternative to split_into_questions(), used when the regex
    heuristic proved unreliable on real papers — it couldn't tell genuine
    question starts apart from other numeric page content (axis labels,
    data tables), producing garbage entries in the question picker.
 
    Reuses ai_matcher.call_claude_api() directly, and the same
    find-the-brackets response-cleaning approach as
    ai_matcher.parse_classification_response(), since the failure mode
    (model prepending prose before the JSON) is identical here.
 
    Costs one API call per page, which is real — accepted deliberately
    after the regex approach was tested against actual extraction
    failures and found insufficient, not as a default choice.
 
    Args:
        page_text (str): cleaned text of one page.
 
    Returns:
        list[str]: one string per detected question. Empty list if the
                    call failed or the page had no real questions.
    """
    prompt = build_llm_split_prompt(page_text)
    raw_response = call_claude_api(prompt)
 
    if raw_response is None:
        return []
 
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
 
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
 
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Could not parse question-split response: {e}")
        return []
 
    # Even with explicit instructions, the model occasionally still returns
    # a stray leftover fragment (e.g. numbers left over from a figure/table
    # caption) alongside genuine questions. Every real question on these
    # papers carries a mark allocation like [3]; fragments don't. Filtering
    # on that is cheap (no extra API call) and reliable, since it's the
    # same signal extract_max_marks() already relies on downstream anyway.
    result = [q for q in result if extract_max_marks(q) is not None]
 
    return result