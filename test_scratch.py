from marking import mark_answer, generate_shadow_question

question_text = "Determine the fundamental (minimum) frequency f0 of the stationary wave that can be formed within this tube. [2]"

mark_scheme_text = """
16(c)(iii) 1/f0 = 2.72 (10^3) or 1/4 x 12.5 = λo/4 or λo = 1.375 (m)
f0 = (340 / 1.375) = 247 (Hz)
C1
A1
Allow length of tube = 0.344 (m)
Allow 250 (Hz) Allow ecf on v from (c)(ii)
"""

max_marks = 2
image_path = "/Users/fatima/Downloads/answer_sample.jpg"

result = mark_answer(question_text, mark_scheme_text, max_marks, image_path)
print("MARKING RESULT:", result)

if result and result["marks_awarded"] < result["max_marks"]:
    spec_description = "the idea that the separation between adjacent nodes (or antinodes) is equal to λ/2"
    shadow = generate_shadow_question(question_text, mark_scheme_text, result["feedback"], spec_description)
    print("SHADOW QUESTION:", shadow)
else:
    print("Full marks — no shadow question needed.")












