import unittest

from features.desktop.desk import desk
from features.whiteboard import ocr, service, shortcuts, teacher
from features.whiteboard.board import PREVIOUS_SESSION, board


def line(x0, y0, x1, y1, steps=8):
    return [[x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps] for i in range(steps + 1)]


def two(x, y, s=60):
    return [[x, y + s * 0.2], [x + s * 0.3, y], [x + s * 0.6, y + s * 0.15], [x + s * 0.55, y + s * 0.45],
            [x + s * 0.1, y + s], [x + s * 0.7, y + s]]


def write(strokes):
    for points in strokes:
        board.stroke(points, "#f4f4f0", 6, False)


def handwritten_two_plus_two():
    return [two(360, 180), line(525, 215, 620, 212), line(570, 188, 562, 252), two(630, 185),
            line(770, 210, 850, 208), line(772, 232, 848, 230)]


class Base(unittest.TestCase):
    def setUp(self):
        board.reset()
        board.ai_enabled = True


class StrokeRecognitionTest(Base):
    def test_a_slanted_handwritten_plus_is_not_read_as_four(self):
        write(handwritten_two_plus_two())
        data = ocr.recognize_math(board.items)
        self.assertEqual(data["expression"], "2+2=")
        self.assertEqual(data["result"], "4")
        self.assertTrue(data["has_equals"])

    def test_atena_text_is_ignored_by_recognition(self):
        board.text("Metodo Perfetto: 242", x=260, y=150, size=34)
        write(handwritten_two_plus_two())
        self.assertEqual(ocr.recognize_math(board.items)["expression"], "2+2=")

    def test_minus_and_division_strokes(self):
        write([two(100, 100), line(200, 130, 260, 131), two(280, 100)])
        self.assertEqual(ocr.recognize_math(board.items)["expression"], "2-2")


class AnswerLayoutTest(Base):
    def test_simple_sum_gets_only_the_result_next_to_the_equals_sign(self):
        write(handwritten_two_plus_two())
        user_boxes = board.occupied()
        res = teacher.auto_evaluate()
        self.assertEqual(res["result"], "4")
        self.assertEqual(res["perfect"], "")
        written = [i for i in board.items if i["by"] == "atena"]
        self.assertEqual([i["text"] for i in written], ["4"])
        self.assertGreater(written[0]["x"], max(b[2] for b in user_boxes))
        self.assertNotIn("Metodo", board.says)

    def test_atena_never_writes_over_the_user(self):
        write(handwritten_two_plus_two())
        user_boxes = board.occupied()
        teacher.teach("47 + 29 =", line=[360, 180, 850, 245], size=50)
        for item in (i for i in board.items if i["by"] == "atena" and i["type"] == "text"):
            x0, y0, x1, y1 = board.bounds(item)
            for ux0, uy0, ux1, uy1 in user_boxes:
                self.assertFalse(x0 < ux1 and x1 > ux0 and y0 < uy1 and y1 > uy0, item["text"])

    def test_perfect_method_is_a_shortcut_for_next_time(self):
        res = teacher.teach("47 + 29 =", line=[100, 100, 400, 160], size=50)
        self.assertEqual(res["result"], "76")
        self.assertIn("Arrotonda 29 a 30", res["perfect"])
        self.assertTrue(any("Metodo perfetto" in i.get("text", "") for i in board.items))

    def test_no_shortcut_for_trivial_operations(self):
        for expression in ("2+2", "3*4", "9-1", "8/2"):
            self.assertEqual(shortcuts.arithmetic(expression), "", expression)
        self.assertIn("×10", shortcuts.arithmetic("12*5"))
        self.assertIn("50²", shortcuts.arithmetic("48*52"))


class OpenBoardTest(Base):
    def tearDown(self):
        service.close_board()

    def test_the_board_opens_empty_and_fullscreen_and_keeps_the_old_work(self):
        service.close_board()
        board.text("vecchio lavoro", x=100, y=100)
        service.open_board()
        self.assertEqual(board.items, [])
        self.assertEqual(len(board.pages), 1)
        self.assertTrue(desk.instances["lavagna"]["fullscreen"])
        self.assertIn(PREVIOUS_SESSION, board.get_save_names())

    def test_an_already_open_board_is_not_wiped(self):
        service.close_board()
        service.open_board()
        board.text("in corso", x=100, y=100)
        service.open_board()
        self.assertEqual([i["text"] for i in board.items], ["in corso"])


if __name__ == "__main__":
    unittest.main()
