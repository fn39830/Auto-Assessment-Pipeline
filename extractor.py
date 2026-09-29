import pdfplumber

def extract_text_from_pdf(pdf_path):
    """
    Opens a PDF file and extracts text from every page.
    Pages with no extractable text are kept as empty strings,
    so the list index always lines up with the real page number
    (page_texts[0] = page 1, page_texts[4] = page 5, etc.).

    Args:
        pdf_path (str): path to the PDF file.

    Returns:
        list[str]: one string per page, in page order.
                    Returns an empty list if the file couldn't be read.
    """
    page_texts = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text is not None:
                    page_texts.append(text)
                else:
                    page_texts.append("")

    except FileNotFoundError:
        print(f"File not found: {pdf_path}")
    except Exception as e:
        print(f"Could not process {pdf_path}: {e}")

    return page_texts


def clean_text(page_text, board=None):

    common_junk = [
        "Turn over",
        "BLANK PAGE",
    ]

    junk_phrases_by_board = {
        "OCR": [
            "© OCR",
            "PMT",
            "OCR is an exempt Charity",
            "Oxford Cambridge and RSA",
        ],
        "AQA": [
            "PMT",
            "IB/G/Jun19/7405/1",
            "outside the box",
            "Do not write",
            "There are no questions printed on this page",
            "DO NOT WRITE ON THIS PAGE",
            "ANSWER IN THE SPACES PROVIDED",
            "continues on the next page",
            "END OF QUESTIONS",
            "Copyright information",
        ],
        "Edexcel": [
            "DO NOT WRITE IN THIS AREA",
            "P52302RA",
            "Total for Question",
        ],
    }

    if board not in junk_phrases_by_board:
        raise ValueError(f"Unknown exam board: {board}")

    junk_phrases = junk_phrases_by_board[board] + common_junk

    lines = page_text.split('\n')

    clean_lines=[]

    for line in lines:
        is_junk = False

        for phrase in junk_phrases:
            if phrase in line:
                is_junk = True
            else:
                pass
        if is_junk:
            pass
        else:
            clean_lines.append(line)

    cleaned_text='\n'.join(clean_lines)


    return cleaned_text

#create a main function that extracts, cleans and saves the pipeline and then save that clean variable
def main():
    """
    Orchestrates the full pipeline: reads catalog.json, extracts text from
    each PDF, cleans it, and saves the result to a new JSON file.
    """
    # Step 1: load catalog.json (built by your indexing script)
    with open("catalog.json", "r") as f:
        catalog = json.load(f)

    all_papers_data = []

    # Step 2: loop through every paper entry in the catalog
    for paper in catalog:
        pdf_path = "past_papers/" + paper["subject"] + "_" + paper["exam_board"] + "_" + paper["year"] + "_" + paper["paper_number"] + ".pdf"

        # Step 3: extract raw text (your function, already built)
        raw_pages = extract_text_from_pdf(pdf_path)

        # Step 4: clean each page (your function, already built)
        cleaned_pages = []
        for page in raw_pages:
            cleaned_pages.append(clean_text(page, board=paper["exam_board"]))

        # Step 5: what should you actually SAVE for each paper?
        # Think: do you want the whole paper's cleaned text as one entry,
        # or per-page? What keys make sense, given catalog.json's structure?
        paper_result = {
            # your decision here
        }

        all_papers_data.append(paper_result)

    # Step 6: save everything to a new file — what should you call it?
    with open("???", "w") as f:
        json.dump(all_papers_data, f)