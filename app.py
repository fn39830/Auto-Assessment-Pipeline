import streamlit as st
import json
from extractor import extract_text_from_pdf
from marking import mark_answer, generate_shadow_question
from stats import get_weakest_spec_points
from stats import record_result

st.set_page_config(
    page_title="Paper Marker",
    page_icon="🖊️",
    layout="centered"
)


# -------------------------------------------------------------------
# Styling
# -------------------------------------------------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Kalam:wght@400;700&family=Inter:wght@400;500;600&display=swap');

.stApp {
    background-color: #1B2E28;
    color: #F0EDE4;
}

h1, h2, h3 {
    font-family: 'Kalam', cursive;
    color: #F0EDE4 !important;
}

p, div, span, label {
    font-family: 'Inter', sans-serif;
}

[data-testid="stSelectbox"] label,
[data-testid="stFileUploader"] label {
    color: #E8C468 !important;
    font-weight: 600;
}

.stButton button {
    background-color: #E8C468;
    color: #1B2E28;
    font-weight: 600;
    border: none;
    border-radius: 6px;
}

.stButton button:hover {
    background-color: #F0D68A;
    color: #1B2E28;
}

[data-testid="stMetricValue"] {
    color: #E8C468;
}

.stAlert {
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)


st.title("🖊️ Paper Marker")
st.caption(
    "Upload your working, get marked against the real scheme, "
    "and practice what you missed."
)


# -------------------------------------------------------------------
# Load data
# -------------------------------------------------------------------

with open("catalog.json", "r") as f:
    catalog = json.load(f)

with open("questions.json", "r") as f:
    questions = json.load(f)

with open("spec_list.json", "r") as f:
    spec_list = json.load(f)


# -------------------------------------------------------------------
# Paper selection
# -------------------------------------------------------------------

paper_lookup = {}

for paper in catalog:
    display_string = (
        f"{paper['subject']} "
        f"{paper['exam_board']} "
        f"{paper['year']} "
        f"Paper {paper['paper_number']}"
    )

    paper_lookup[display_string] = paper


selected_display = st.selectbox(
    "Paper",
    list(paper_lookup.keys())
)

selected_paper = paper_lookup[selected_display]

paper_prefix = (
    f"{selected_paper['subject']}_"
    f"{selected_paper['exam_board']}_"
    f"{selected_paper['year']}_"
    f"{selected_paper['paper_number']}"
)


# -------------------------------------------------------------------
# Find questions for selected paper
# -------------------------------------------------------------------

questions_in_paper = {}

for question_id, question in questions.items():
    if question_id.startswith(paper_prefix):
        questions_in_paper[question_id] = question


# -------------------------------------------------------------------
# Tabs
# -------------------------------------------------------------------

marker_tab, specification_tab = st.tabs(
    ["🖊️ Paper Marker", "🗺️ Specification Map"]
)


# ===================================================================
# PAPER MARKER
# ===================================================================

with marker_tab:

    # ---------------------------------------------------------------
    # Mark scheme
    # ---------------------------------------------------------------

    mark_scheme_path = (
        f"mark_schemes/{paper_prefix}_MS.pdf"
    )

    mark_scheme_pages = extract_text_from_pdf(
        mark_scheme_path
    )

    mark_scheme_text = "\n".join(mark_scheme_pages)

    if not mark_scheme_text.strip():
        st.warning(
            f"No mark scheme found for this paper "
            f"(expected at `{mark_scheme_path}`). "
            "Marking will proceed using Claude's general knowledge "
            "only, not the real mark scheme — treat the result as "
            "a rough estimate."
        )


    # ---------------------------------------------------------------
    # Question selection
    # ---------------------------------------------------------------

    question_display = {}

    for question_id in questions_in_paper:
        short_label = question_id.replace(
            paper_prefix + "_",
            ""
        )

        question_display[short_label] = question_id


    if not question_display:
        st.error("No questions were found for this paper.")
        st.stop()


    selected_short_label = st.selectbox(
        "Question",
        list(question_display.keys())
    )

    selected_question_id = question_display[
        selected_short_label
    ]

    details = questions_in_paper[selected_question_id]

    question_text = details["text"]
    max_marks = details["max_marks"]


    st.divider()

    st.subheader("Question")
    st.write(question_text)

    st.metric(
        "Marks Available",
        max_marks
    )


    # ---------------------------------------------------------------
    # Answer upload and marking
    # ---------------------------------------------------------------

    st.subheader("Upload your answer")

    temp_file_upload = st.file_uploader(
        "Upload a photo of your answer",
        type=["jpg", "jpeg", "png"]
    )


    if temp_file_upload is not None:

        image_path = "temp_answer.jpg"

        with open(image_path, "wb") as f:
            f.write(temp_file_upload.read())


        if st.button("Mark my answer"):

            with st.spinner("Marking your answer..."):

                result = mark_answer(
                    question_text,
                    mark_scheme_text,
                    max_marks,
                    image_path
                )


            if result is None:

                st.error(
                    "Marking failed — the response couldn't be read. "
                    "Try again."
                )

            else:

                record_result(
                    details["spec_code"],
                    result["marks_awarded"],
                    result["max_marks"]
                )

                st.divider()
                st.subheader("Result")

                col1, col2 = st.columns(2)

                with col1:
                    st.metric(
                        "Marks Awarded",
                        f"{result['marks_awarded']} / "
                        f"{result['max_marks']}"
                    )

                with col2:
                    st.progress(
                        result["marks_awarded"]
                        / result["max_marks"]
                        if result["max_marks"]
                        else 0
                    )


                if result["marks_awarded"] == result["max_marks"]:

                    st.success(
                        f"Full marks! {result['feedback']}"
                    )

                else:

                    st.warning(
                        result["feedback"]
                    )


                # Store result so it survives Streamlit reruns
                st.session_state["last_result"] = result
                st.session_state["last_question_text"] = question_text
                st.session_state["last_mark_scheme"] = mark_scheme_text
                st.session_state["last_spec_description"] = (
                    details.get("description", "")
                )


    # ---------------------------------------------------------------
    # Shadow question
    # ---------------------------------------------------------------

    if "last_result" in st.session_state:

        result = st.session_state["last_result"]

        if result["marks_awarded"] < result["max_marks"]:

            st.divider()

            st.subheader("Practice question")

            st.write(
                "You didn't get full marks on this one. "
                "Want a similar question to practice?"
            )


            if st.button("Generate a practice question"):

                with st.spinner(
                    "Generating a practice question..."
                ):

                    shadow = generate_shadow_question(
                        st.session_state["last_question_text"],
                        st.session_state["last_mark_scheme"],
                        result["feedback"],
                        st.session_state["last_spec_description"],
                    )


                if shadow is None:

                    st.error(
                        "Couldn't generate a practice question — "
                        "try again."
                    )

                else:

                    st.success(
                        "Here's a new one to try:"
                    )

                    st.write(
                        shadow["new_question"]
                    )

                    with st.expander("Mark scheme"):

                        st.write(
                            shadow["new_mark_scheme"]
                        )


# ===================================================================
# SPECIFICATION MAP
# ===================================================================

with specification_tab:

    st.subheader("Specification Map")

    st.write(
        "Explore which specification points are covered by the "
        "questions in your question bank."
    )


    # ---------------------------------------------------------------
    # Filter specification list to current subject + exam board
    # ---------------------------------------------------------------

    selected_subject = selected_paper["subject"]
    selected_board = selected_paper["exam_board"]


    relevant_specs = [
        spec for spec in spec_list
        if spec["subject"] == selected_subject
        and spec["exam_board"] == selected_board
    ]


    # ---------------------------------------------------------------
    # Match questions to specification points
    #
    # questions.json:
    #     "spec_code": "4.4.4d"
    #
    # spec_list.json:
    #     "tag": "4.4.4d"
    # ---------------------------------------------------------------

    spec_questions = {}

    for question_id, question in questions.items():

        spec_code = question.get("spec_code")

        if not spec_code:
            continue

        # Only include questions belonging to the current
        # subject + exam board.
        if not question_id.startswith(
            f"{selected_subject}_{selected_board}_"
        ):
            continue

        spec_questions.setdefault(
            spec_code,
            []
        ).append(question_id)


    # ---------------------------------------------------------------
    # Overview
    # ---------------------------------------------------------------

    covered_count = sum(
        1
        for spec in relevant_specs
        if spec["tag"] in spec_questions
    )

    total_count = len(relevant_specs)

    coverage_percentage = (
        covered_count / total_count * 100
        if total_count
        else 0
    )


    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Specification Points",
            total_count
        )

    with col2:
        st.metric(
            "Points With Questions",
            covered_count
        )

    with col3:
        st.metric(
            "Coverage",
            f"{coverage_percentage:.1f}%"
        )


    st.divider()


    # ---------------------------------------------------------------
    # Specification coverage by module
    #
    # The first number in a code such as 4.4.4d is used as the
    # top-level module. The JSON does not contain module names,
    # so we display "Module 4", "Module 6", etc.
    # ---------------------------------------------------------------

    st.subheader("Coverage by module")


    module_data = {}

    for spec in relevant_specs:

        tag = spec["tag"]

        module = tag.split(".")[0]

        if module not in module_data:
            module_data[module] = {
                "total": 0,
                "covered": 0
            }

        module_data[module]["total"] += 1

        if tag in spec_questions:
            module_data[module]["covered"] += 1


    for module in sorted(
        module_data,
        key=lambda x: int(x)
    ):

        data = module_data[module]

        percentage = (
            data["covered"]
            / data["total"]
            * 100
            if data["total"]
            else 0
        )

        st.write(
            f"**Module {module}** — "
            f"{data['covered']} / {data['total']} "
            f"points covered"
        )

        st.progress(
            percentage / 100
        )


    st.divider()


    # ---------------------------------------------------------------
    # Specification point explorer
    # ---------------------------------------------------------------

    st.subheader("Specification point explorer")

    spec_lookup = {
        spec["tag"]: spec
        for spec in relevant_specs
    }


    spec_options = [
        spec["tag"]
        for spec in relevant_specs
    ]


    if spec_options:

        selected_spec_code = st.selectbox(
            "Choose a specification point",
            spec_options
        )

        selected_spec = spec_lookup[
            selected_spec_code
        ]


        st.markdown(
            f"### `{selected_spec_code}`"
        )

        st.write(
            selected_spec["description"]
        )


        mapped_question_ids = spec_questions.get(
            selected_spec_code,
            []
        )


        if not mapped_question_ids:

            st.info(
                "No questions in the current question bank "
                "are mapped to this specification point."
            )

        else:

            st.write(
                f"**{len(mapped_question_ids)} "
                f"question(s) mapped to this point:**"
            )


            for question_id in mapped_question_ids:

                question = questions[question_id]

                st.markdown(
                    f"**{question_id}** — "
                    f"{question['max_marks']} mark(s)"
                )

                st.write(
                    question["text"]
                )

                st.divider()


    st.divider()


    # ---------------------------------------------------------------
    # Weakest / most-missed specification points
    # ---------------------------------------------------------------

    st.subheader("Most-missed specification points")

    st.caption(
        "Based on your recorded marking results. "
        "Only attempted questions can contribute to this."
    )


    try:

        weakest_points = get_weakest_spec_points()

    except Exception:

        weakest_points = []


    if not weakest_points:

        st.info(
            "No missed specification points recorded yet."
        )

    else:

        # Convert the stats output into a simple list so the UI
        # can handle the common dictionary / tuple formats.
        rows = []

        for item in weakest_points:

            if isinstance(item, dict):

                code = item.get(
                    "spec_code",
                    item.get("tag")
                )

                count = item.get(
                    "count",
                    item.get(
                        "misses",
                        item.get("missed", 0)
                    )
                )

            elif isinstance(item, (list, tuple)) and len(item) >= 2:

                code = item[0]
                count = item[1]

            else:

                continue


            if code is None:
                continue


            spec = spec_lookup.get(code)

            if spec is None:
                continue


            rows.append(
                (
                    code,
                    count,
                    spec["description"]
                )
            )


        if not rows:

            st.info(
                "No missed specification points recorded yet."
            )

        else:

            for code, count, description in rows[:10]:

                st.markdown(
                    f"**{code}** — {count} miss(es)"
                )

                st.caption(
                    description
                )