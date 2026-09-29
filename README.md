# A-Level Paper Marker

An AI-powered tool that marks a photographed A-Level exam answer against the
real mark scheme, maps the question to its specification point, and
generates a fresh practice question if you didn't get full marks.

## What it does

1. Pick a past paper and question from the dropdown.
2. Upload a photo of your handwritten or typed answer.
3. Claude reads the photo directly (no OCR step), marks it against the real
   mark scheme, and returns a score plus feedback.
4. If you didn't get full marks, generate a new practice question testing
   the same concept — with its own mark scheme.
5. A running tally tracks which specification points you get wrong most
   often.

## Architecture

- **C++ engine** (`engine.h`, `engine.cpp`, `binding.cpp`) — stores
  specification points and provides fast lookup by tag, exposed to Python
  via [pybind11](https://pybind11.readthedocs.io/) as a compiled module
  (`spec_engine`).
- **Python pipeline** (`extractor.py`, `question_splitter.py`,
  `ai_matcher.py`, `bridge.py`, `marking.py`, `stats.py`, `main.py`) —
  extracts text from past papers, splits it into individual questions,
  classifies each against the specification via the Claude API, and
  handles marking and practice-question generation.
- **Streamlit frontend** (`app.py`) — lets a student pick a paper/question,
  upload a photo, and see their result.

The C++/Python split exists because the project's original stack called
for a high-performance C++ core for spec-point lookup, bridged to a Python
orchestration layer via pybind11.

## Setup

1. Clone the repository and create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Compile the C++ engine into a Python-importable module:
   ```bash
   c++ -O3 -Wall -shared -undefined dynamic_lookup -std=c++17 -fPIC $(python3 -m pybind11 --includes) binding.cpp -o spec_engine$(python3-config --extension-suffix)
   ```
   (On Linux, drop `-undefined dynamic_lookup` — it's a macOS linker flag.)

4. Create a `.env` file in the project root with your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=your-key-here
   ```

5. Add your own past papers, mark schemes, and specifications — see
   [Copyright and past papers](#copyright-and-past-papers) below, and
   `SPEC_LIST_TODO.md` for the required `spec_list.json` format.

6. Build the catalog and question index:
   ```bash
   python3 indexer.py
   python3 main.py
   ```

7. Run the app:
   ```bash
   streamlit run app.py
   ```

## Copyright and past papers

This repository does **not** include any OCR past papers, mark schemes, or
specification documents. Under
[OCR's copyright policy](https://www.ocr.org.uk/about/our-policies/copyright/),
permission-free reproduction of these materials is granted only to
approved exam centres, for internal/private use — not for public
redistribution, which is what a public GitHub repository would
constitute.

To run this project, you'll need your own legally obtained copies of the
relevant past papers, mark schemes, and specifications (e.g. downloaded
directly from [ocr.org.uk](https://ocr.org.uk) for personal revision use),
placed in `past_papers/` and `mark_schemes/` respectively, with spec
points added to `spec_list.json`. None of this content is bundled with or
distributed by this repository — see `.gitignore`.

## Known limitations

- **Question splitting is a heuristic, not a guaranteed-correct parser.**
  An earlier regex-based approach couldn't reliably distinguish real
  question starts from other numeric page content (graph axis labels,
  data tables) — both look identical at the pattern-matching level. This
  was replaced with an LLM-based splitter (`split_into_questions_llm`),
  which reads each page holistically instead of pattern-matching line by
  line.
- **Mark schemes aren't parsed into a structured format.** Given how
  inconsistently exam board mark schemes are laid out (scattered mark
  codes, a "guidance" column collapsed into the main text on extraction,
  Level-of-Response rubrics that don't fit a uniform structure), the raw
  extracted text is passed to Claude directly, which locates the relevant
  marking points itself rather than relying on a fragile offline parser.
- **Tested on a small number of real papers** (Physics and Maths, OCR),
  not validated across every exam board or subject.

## Key design decisions

- **Manual specification lists over automated parsing.** An automated
  parser for spec PDFs was built and then abandoned after testing exposed
  a genuine ambiguity: when two lettered sub-points share a line with no
  separating text, there's no way to recover which content belongs to
  which letter. `spec_list.json` is filled in by hand instead.
- **Composite question IDs** (e.g. `Physics_OCR_2022_2_Q1`) rather than
  simple per-batch counters, so IDs stay globally unique across the whole
  dataset — this matters for the AI classification step, which matches
  results back to questions by ID rather than relying on response order
  (an ordering mismatch would otherwise cascade into misaligned results
  for every subsequent item).
- **Batching with partial-failure isolation.** Classification requests are
  batched (15 questions per call, scoped to one paper), and if a subset of
  a batch's responses is missing or malformed, only those specific items
  are retried in a smaller follow-up call — not the whole batch.
- **A single output shape for practice-question generation**, rather than
  branching into differently-shaped outputs (e.g. a full question vs. a
  multiple-choice quiz) depending on why marks were lost. The generation
  prompt still diagnoses *why* marks were lost (a structural/exam-technique
  gap vs. a conceptual/knowledge gap) and shapes the new question
  accordingly, but always returns the same `{new_question, new_mark_scheme}`
  structure — a deliberate scope cut given the project timeline.