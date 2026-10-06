import base64
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from features.whiteboard import board as board_module
from features.whiteboard import science, teacher_kit
from features.whiteboard.board import BOTTOM, COLUMN_WIDTH, Board
from features.whiteboard.pdf_exporter import export_pages_to_pdf

PNG = "data:image/png;base64," + base64.b64encode(
    bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                  "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")).decode()


class ScienceTest(unittest.TestCase):
    def test_chemistry(self):
        self.assertEqual(science.balance("C3H8 + O2 -> CO2 + H2O")["equation"], "C₃H₈ + 5O₂ → 3CO₂ + 4H₂O")
        self.assertEqual(science.balance("Fe + O2 = Fe2O3")["coefficients"], [4, 3, 2])
        self.assertAlmostEqual(science.molar_mass("Ca(OH)2")["total"], 74.092, places=2)
        self.assertAlmostEqual(science.molar_mass("CuSO4·5H2O")["total"], 249.68, places=1)
        self.assertEqual(science.chem("SO4^2-"), "SO₄²⁻")
        for bad in ("Xx2", "H2(O", "", "H2 + O2"):
            with self.subTest(bad=bad), self.assertRaises(science.ScienceError):
                science.balance(bad) if "+" in bad else science.molar_mass(bad)

    def test_calculus_and_plot(self):
        self.assertEqual(science.calculus("derivative", "x^2")["plain"], "2*x")
        self.assertEqual(science.calculus("integral", "2*x")["plain"], "x^2")
        self.assertEqual(science.calculus("limit", "sin(x)/x", "0")["plain"], "1")
        self.assertEqual(science.calculus("limit", "1/x", "oo")["plain"], "0")
        data = science.sample("1/x", -5, 5)
        self.assertEqual(len(data["points"]), science.SAMPLES)
        self.assertTrue(any(p[1] is None for p in data["points"]))
        self.assertLess(data["ymax"], 50)

    def test_physics_with_units(self):
        self.assertEqual(science.physics("F = m*a", {"m": "2 kg", "a": "3 m/s^2"}, "F")["result"], "F = 6 N")
        self.assertEqual(science.physics("a = F/m", {"F": "10 N", "m": "2 kg"}, "a")["result"], "a = 5 m/s²")
        self.assertEqual(science.physics("R = V/I", {"V": "12 V", "I": "0.5 A"}, "R")["result"], "R = 24 Ω")
        self.assertIn("J", science.physics("E = m*c^2", {"m": "1 kg", "c": "299792458 m/s"}, "E")["result"])
        with self.assertRaises(science.ScienceError):
            science.physics("F = m*a", {"m": "2 kg"}, "F")

    def test_parser_rejects_code(self):
        for bad in ("__import__('os')", "x**99999", "open('a')", "lambda: 1", "().__class__", "x" * 300):
            with self.subTest(bad=bad), self.assertRaises(science.ScienceError):
                science.parse(bad)


class BoardLayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(board_module, "FILE", Path(self.tmp.name) / "wb.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.b = Board()

    def test_text_wraps_inside_the_column(self):
        rows = self.b.paragraph("parola " * 60, size=40)
        self.assertGreater(len(rows), 3)
        for row in rows:
            self.assertLessEqual(len(row["text"]) * 40 * 0.55, COLUMN_WIDTH + 40)
        self.assertEqual({r["x"] for r in rows}, {60})

    def test_full_board_continues_on_a_new_page(self):
        for i in range(60):
            self.b.text(f"riga {i}", size=42)
        self.assertGreater(len(self.b.pages), 1)
        self.assertTrue(all(i["y"] + 42 <= BOTTOM for p in self.b.pages for i in p["items"]))

    def test_rich_items_are_validated(self):
        self.b.callout("tip", "Ricorda", "Il quadrato di un binomio")
        self.b.chart("pie", ["a", "b"], [1, 3], "Torta")
        self.b.table(["it", "en"], [["cane", "dog"], ["gatto", "cat"]])
        self.b.formula(["x² + 1"], "f(x)")
        self.b.image(PNG, "pixel")
        for call in (lambda: self.b.callout("evil", "t", "x"), lambda: self.b.chart("pie", ["a"], [-1]), lambda: self.b.chart("bar", ["a"], ["x"]),
                     lambda: self.b.image("data:image/svg+xml;base64,PHN2Zz4=", ""), lambda: self.b.image("javascript:alert(1)", ""),
                     lambda: self.b.image("data:image/png;base64," + base64.b64encode(b"not a png").decode(), ""),
                     lambda: self.b.mark("glitter", 0, 0, 1, 1), lambda: self.b.mark("box", 0, 0, 1, 1, target=99999)):
            with self.assertRaises(ValueError):
                call()

    def test_marks_wrap_their_target(self):
        row = self.b.text("teorema di Pitagora", size=40)
        mark = self.b.mark("circle", 0, 0, 0, 0, target=row["id"])
        self.assertEqual((mark["x1"], mark["y1"]), (row["x"], row["y"]))
        self.assertGreater(mark["x2"], row["x"])

    def test_pdf_renders_rich_items(self):
        self.b.callout("info", "Nota", "testo")
        self.b.plot([{"label": "x", "points": [[0, 0], [1, 1]]}], 0, 1, 0, 1, "retta")
        self.b.chart("bar", ["a", "b"], [1, 2])
        self.b.table(["a"], [["b"]])
        self.b.image(PNG, "")
        self.b.mark("strike", 10, 10, 50, 20)
        self.assertTrue(export_pages_to_pdf([{"items": self.b.items}]).startswith(b"%PDF"))


class TeacherKitTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(board_module, "FILE", Path(self.tmp.name) / "wb.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.board = Board()
        swap = mock.patch.object(teacher_kit, "board", self.board)
        swap.start()
        self.addCleanup(swap.stop)

    async def test_lesson_renders_every_block_kind_and_skips_broken_ones(self):
        lesson = {"title": "Parabola", "summary": "Ecco la parabola.", "blocks": [
            {"type": "text", "text": "Una parabola è il grafico di un polinomio di secondo grado."},
            {"type": "steps", "items": ["trova il vertice", "trova le radici"]},
            {"type": "callout", "kind": "definition", "title": "Vertice", "text": "Il punto di minimo o massimo."},
            {"type": "formula", "expression": "(x+1)^2"}, {"type": "plot", "functions": ["x^2", "2*x+1"], "xmin": -3, "xmax": 3},
            {"type": "chart", "kind": "bar", "labels": ["a", "b"], "values": [1, 2]}, {"type": "table", "header": ["x", "y"], "rows": [["0", "1"]]},
            {"type": "chemistry", "reaction": "H2 + O2 -> H2O"}, {"type": "formula", "expression": "__import__('os')"}, {"type": "evil"}]}
        with mock.patch("features.brain.llm.generate", mock.AsyncMock(return_value=lesson)):
            result = await teacher_kit.lesson("la parabola", "it", "math")
        self.assertEqual(result["blocks"], 8)
        kinds = {i["type"] for p in self.board.pages for i in p["items"]}
        self.assertTrue({"text", "callout", "formula", "plot", "chart", "table"} <= kinds)
        self.assertEqual(self.board.says, "Ecco la parabola.")

    async def test_images_only_free_licensed_from_wikimedia_with_credit(self):
        class Response:
            def __init__(self, status, payload=None, content=b"", kind="application/json"):
                self.status_code, self._payload, self.content, self.headers = status, payload, content, {"content-type": kind}

            def json(self):
                return self._payload

        def page(thumb, license_name):
            return {"query": {"pages": {"1": {"index": 1, "title": "File:Colosseo.jpg", "imageinfo": [{
                "thumburl": thumb, "mime": "image/jpeg", "width": 1200, "thumbwidth": 900, "thumbheight": 600,
                "descriptionshorturl": "https://commons.wikimedia.org/w/index.php?curid=1",
                "extmetadata": {"LicenseShortName": {"value": license_name}, "Artist": {"value": "<a>Mario Rossi</a>"}}}]}}}}

        class Client:
            def __init__(self, thumb, license_name="CC BY-SA 4.0"):
                self.thumb, self.license = thumb, license_name

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url, params=None):
                if params is not None:
                    return Response(200, page(self.thumb, self.license))
                return Response(200, content=base64.b64decode(PNG.split(",")[1]), kind="image/png")

        with mock.patch.object(teacher_kit.httpx, "AsyncClient", lambda **kw: Client("https://upload.wikimedia.org/a.png")):
            item = await teacher_kit.image("Colosseo")
        self.assertIsNotNone(item)
        self.assertIn("Mario Rossi", item["caption"])
        self.assertIn("CC BY-SA 4.0", item["caption"])
        with mock.patch.object(teacher_kit.httpx, "AsyncClient", lambda **kw: Client("https://evil.example/a.png")):
            self.assertIsNone(await teacher_kit.image("Colosseo"))
        with mock.patch.object(teacher_kit.httpx, "AsyncClient", lambda **kw: Client("https://upload.wikimedia.org/a.png", "CC BY-NC 4.0")):
            self.assertIsNone(await teacher_kit.image("Colosseo"))
        with mock.patch.object(teacher_kit.httpx, "AsyncClient", lambda **kw: Client("https://upload.wikimedia.org/a.png", "Fair use")):
            self.assertIsNone(await teacher_kit.image("Colosseo"))

    async def test_science_helpers_write_to_the_board(self):
        teacher_kit.molar_mass("H2SO4")
        teacher_kit.balance("H2 + O2 -> H2O")
        teacher_kit.physics("F = m*a", {"m": "2 kg", "a": "3 m/s^2"}, "F")
        teacher_kit.calculus("derivative", "x^3")
        self.assertEqual(teacher_kit.highlight_last("highlight", 2), 2)
        texts = " ".join(i.get("text", "") for i in self.board.items)
        self.assertIn("98.072", texts)
        self.assertIn("2H₂ + O₂ → 2H₂O", texts)
        self.assertIn("F = 6 N", texts)


class VoiceScienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_voice_patterns(self):
        from features.whiteboard import commands
        with tempfile.TemporaryDirectory() as root, mock.patch.object(board_module, "FILE", Path(root) / "wb.json"):
            fresh = Board()
            with mock.patch.object(teacher_kit, "board", fresh):
                cases = {"calcola la massa molare di H2SO4 alla lavagna": "98.072", "bilancia la reazione C3H8 + O2 -> CO2 + H2O": "5O₂",
                         "fai la derivata di x^3 alla lavagna": "3*x^2", "disegna il grafico di x^2 da -3 a 3 alla lavagna": "grafico"}
                for text, expected in cases.items():
                    reply, _ = await commands.science(text, commands.plain(text))
                    self.assertIn(expected, reply, text)
            self.assertIsNone(await commands.science("accendi la luce", "accendi la luce"))


if __name__ == "__main__":
    unittest.main()
