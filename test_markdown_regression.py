"""
test_markdown_regression.py - Regression test for HTML-as-code markdown bug.
Verifies that no st.markdown element containing '<div' or '<style' has 4 or more leading spaces.
"""
import unittest
from streamlit.testing.v1 import AppTest


class TestMarkdownLeadingSpaces(unittest.TestCase):
    def test_markdown_no_indented_html(self):
        at = AppTest.from_file("app.py").run()
        tested_elements = 0
        for i, m in enumerate(at.markdown):
            body = m.value
            if "<div" in body or "<style" in body:
                non_empty = [line for line in body.splitlines() if line.strip()]
                if non_empty:
                    tested_elements += 1
                    first_line = non_empty[0]
                    leading_spaces = len(first_line) - len(first_line.lstrip(" "))
                    self.assertLess(
                        leading_spaces,
                        4,
                        f"Markdown element #{i} has {leading_spaces} leading spaces (HTML-as-code bug):\n{first_line}"
                    )
        self.assertGreater(tested_elements, 0, "Expected at least one HTML markdown element to be tested.")


if __name__ == "__main__":
    unittest.main()

