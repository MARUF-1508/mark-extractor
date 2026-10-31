"""Independently transcribed rightmost columns from the supplied printed sheets."""
CSE_MARKS = """
39 33.5 36 28 31 26.5 31.5 30 28 26.5 33 37 30.5 33 33.5 37 29.5
28.5 34 1.2 27.5 30 32.5 34 32 35 34 33.5 37.5 36.5 30.5 34.5 1.2 39.5 37.5 30
38 36 27 33 24 33 37.5 39.5 37.5 36.5 29.5 36 30 37 36 35.5 33.5 34
""".split()
CSE_ROLLS = [str(i) for i in range(328, 380)] + ["2051", "2052"]

OOAD_MARKS = """
18 15 15 9 13 14 16 9 9 12 16 13 18 12 12 16 14 9 17 13 16 17 15 14.5 13 18 9
16 17 13 9 10 18 12 16 16 10 14 9 10 17 12 13 12 10 11 10 13 17 12.5 12 10
""".split()
OOAD_ROLLS = [str(i) for i in range(328, 380) if i not in (347, 360)] + ["2051", "2052"]

SAMPLES = [
    ("CSE 251_CT_marks.pdf", list(zip(CSE_ROLLS, CSE_MARKS)), [17, 19, 18], "Total (40)", 40),
    ("OOAD_tutorial.pdf", list(zip(OOAD_ROLLS, OOAD_MARKS)), [27, 25], "Project(20)", 20),
]
