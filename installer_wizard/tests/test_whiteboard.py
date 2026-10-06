import asyncio
import base64
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from features.agent import registry
from features.capabilities import mcp
from features.desktop.desk import desk
from features.whiteboard import api, board as board_module, commands, ocr, service, solver, tools
from features.whiteboard.board import Board

JPEG = b"\xff\xd8" + b"x" * 500


def lines(text: str) -> list[str]:
    return solver.solve(text)["lines"]


class SolverTest(unittest.TestCase):
    def test_arithmetic_is_solved_step_by_step_like_at_school(self):
        self.assertEqual(lines("12 x (3 + 4)"), ["12 × (3 + 4)", "= 12 × 7", "= 84"])
        self.assertEqual(lines("2+3*4"), ["2 + 3 × 4", "= 2 + 12", "= 14"])
        self.assertEqual(lines("(1+2)*(3+4)-5")[-1], "= 16")
        self.assertEqual(lines("10 per 3 meno 4"), ["10 × 3 − 4", "= 30 − 4", "= 26"])
        self.assertEqual(lines("100 diviso 8"), ["100 ÷ 8", "= 12,5"])
        self.assertEqual(lines("2 alla 10")[-1], "= 1024")
        self.assertEqual(lines("3 - -5"), ["3 − (−5)", "= 8"])
        self.assertIn("2,3333", lines("7/3")[-1])
        self.assertEqual(solver.solve("12 x 5")["speech"], "12 × 5 fa 60.")

    def test_first_degree_equations_show_every_move(self):
        self.assertEqual(lines("2x + 3 = 11"), ["2x + 3 = 11", "2x = 11 − 3", "2x = 8", "x = 8 ÷ 2", "x = 4"])
        self.assertEqual(lines("3x - 5 = x + 9")[-1], "x = 7")
        self.assertEqual(lines("2(x+1)=10")[-1], "x = 4")
        self.assertEqual(lines("x/4 = 3")[-1], "x = 12")
        self.assertEqual(lines("-6x=12")[-1], "x = −2")
        self.assertEqual(solver.solve("2x + 3 = 11")["speech"], "x vale 4.")
        self.assertEqual(solver.solve("x + 1 = x + 2")["result"], "non ha soluzioni")
        self.assertIn("infinite", solver.solve("x + 1 = x + 1")["result"])

    def test_bad_input_is_refused_with_a_reason(self):
        for text in ("", "1 / 0", "2 alla 99", "x*x = 4", "2x + 3y = 5", "5 = 5", "3 +", "abc", "9" * 200, "__import__('os')"):
            with self.assertRaises(ValueError, msg=text):
                solver.solve(text)


class BoardTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(board_module, "FILE", Path(folder.name) / "b.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.board = Board()

    def test_text_flows_down_into_a_second_column_then_onto_a_new_page(self):
        first = self.board.text("uno", size=40)
        second = self.board.text("due", size=40)
        self.assertEqual((first["x"], second["x"]), (60, 60))
        self.assertGreater(second["y"], first["y"])
        columns = set()
        while len(self.board.pages) == 1:
            columns.add(self.board.text("riga", size=40)["x"])
        self.assertEqual(columns, set(board_module.COLUMNS))
        self.assertEqual(self.board.page_index, 1)
        self.assertEqual(self.board.items[-1]["x"], board_module.COLUMNS[0])

    def test_values_are_clamped_and_validated(self):
        item = self.board.text("ciao", x=99999, y=-5, size=9999, ink="rosso")
        self.assertEqual((item["x"], item["y"], item["size"], item["color"]), (board_module.WIDTH, 0, 140, board_module.ATENA_INK))
        with self.assertRaises(ValueError):
            self.board.text("   ")
        with self.assertRaises(ValueError):
            self.board.shape("stella", 0, 0, 1, 1)
        with self.assertRaises(ValueError):
            self.board.stroke([], "#ffffff", 4, False)
        stroke = self.board.stroke([[10, 10], [5000, -3], "x", [1]], "#ffffff", 400, False)
        self.assertEqual(stroke["points"], [[10, 10], [board_module.WIDTH, 0]])
        self.assertEqual(stroke["width"], 60)
        self.assertEqual(self.board.shape("arrow", 1, 2, 3, 4, "#abcdef")["type"], "arrow")
        self.assertEqual(len(self.board.text("a" * 500)["text"]), board_module.MAX_TEXT)

    def test_undo_clear_persistence_and_snapshot(self):
        self.board.text("mio")
        self.board.stroke([[1, 1], [2, 2]], "#ffffff", 4, False, by="user")
        self.assertTrue(self.board.undo("user"))
        self.assertFalse(self.board.undo("user"))
        self.assertEqual([i["by"] for i in self.board.items], ["atena"])
        again = Board()
        self.assertEqual(again.items[0]["text"], "mio")
        self.assertEqual(again.counter, self.board.counter)
        before = self.board.rev
        self.assertEqual(self.board.clear(), 1)
        self.assertGreater(self.board.rev, before)
        self.assertEqual(Board().items, [])
        with self.assertRaises(ValueError):
            self.board.set_snapshot(b"non una jpeg")
        with self.assertRaises(ValueError):
            self.board.set_snapshot(JPEG + b"x" * board_module.MAX_SNAPSHOT)
        self.board.set_snapshot(JPEG)
        self.assertEqual(self.board.snapshot, JPEG)

    def test_the_board_refuses_to_grow_without_limit(self):
        with mock.patch.object(board_module, "MAX_ITEMS", 3):
            for _ in range(3):
                self.board.shape("line", 0, 0, 5, 5)
            with self.assertRaises(ValueError):
                self.board.shape("line", 0, 0, 5, 5)


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(board_module, "FILE", Path(folder.name) / "b.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.board = Board()
        from features.whiteboard import teacher
        for module in (service, commands, tools, api, teacher):
            patcher = mock.patch.object(module, "board", self.board)
            patcher.start()
            self.addCleanup(patcher.stop)
        desk.scan()
        saved = dict(desk.instances)
        desk.instances.clear()
        self.addCleanup(lambda: (desk.instances.clear(), desk.instances.update(saved)))

    def say(self, text: str) -> str:
        return asyncio.run(commands.answer(text))[0]

    def texts(self) -> list[str]:
        return [i["text"] for i in self.board.items if i["type"] == "text"]


class VoiceTest(Base):
    def test_the_widget_exists_and_opens_fullscreen_by_voice(self):
        self.assertIn("lavagna", desk.widgets)
        self.assertIn("tutto schermo", self.say("apri la lavagna a tutto schermo"))
        self.assertTrue(service.is_open())
        instance = desk.instances["lavagna"]
        self.assertTrue(instance["fullscreen"])
        self.assertIsNone(instance["expires_at"])
        self.assertIn("normale", self.say("schermo normale"))
        self.assertFalse(desk.instances["lavagna"]["fullscreen"])
        self.say("metti a tutto schermo")
        self.assertTrue(desk.instances["lavagna"]["fullscreen"])

    def test_unrelated_requests_are_left_to_the_other_connectors(self):
        for text in ("calcola 5 per 5", "che tempo fa", "metti la musica", "apri la webcam"):
            with self.assertRaises(LookupError, msg=text):
                self.say(text)
        self.say("apri la lavagna")
        for text in ("che tempo fa", "metti la musica di Vasco"):
            with self.assertRaises(LookupError, msg=text):
                self.say(text)

    def test_calculations_and_equations_are_written_step_by_step(self):
        self.assertIn("84", self.say("calcola 12 per (3 più 4) alla lavagna"))
        self.assertTrue(service.is_open())
        self.assertEqual(self.texts(), ["12 × (3 + 4)", "= 12 × 7", "= 84"])
        self.assertEqual({i["color"] for i in self.board.items}, {board_module.ATENA_INK, service.TITLE_INK, service.RESULT_INK})
        self.assertEqual(self.board.says, "12 × (3 + 4) fa 84.")
        self.say("risolvi 2x + 3 = 11")
        self.assertEqual(self.texts()[-1], "x = 4")
        self.assertIn("Non riesco", self.say("calcola 5 diviso 0"))

    def test_writing_undo_clear_and_close(self):
        self.say("apri la lavagna")
        self.assertIn("Scritto", self.say("scrivi sulla lavagna il teorema di Pitagora"))
        self.assertEqual(self.texts(), ["il teorema di pitagora"])
        self.board.stroke([[1, 1], [9, 9]], "#ffffff", 4, False)
        self.assertIn("cancellato", self.say("annulla"))
        self.assertEqual([i["by"] for i in self.board.items], ["atena"])
        self.assertIn("pulita", self.say("cancella la lavagna"))
        self.assertEqual(self.board.items, [])
        self.assertIn("chiuso", self.say("chiudi la lavagna"))
        self.assertFalse(service.is_open())
        self.assertIn("non era aperta", self.say("chiudi la lavagna"))
        with self.assertRaises(LookupError):
            self.say("cancella la lavagna")

    def test_explaining_writes_a_title_and_the_steps(self):
        reply = {"titolo": "Fotosintesi", "passi": ["La pianta assorbe luce", "CO2 + acqua", "produce zucchero e ossigeno"], "riassunto": "Ecco la fotosintesi."}
        with mock.patch("features.brain.llm.generate", mock.AsyncMock(return_value=reply)):
            self.assertEqual(self.say("spiegami la fotosintesi alla lavagna"), "Ecco la fotosintesi.")
        self.assertEqual(self.texts()[0], "Fotosintesi")
        self.assertEqual(len(self.texts()), 4)
        self.assertTrue(service.is_open())
        with mock.patch("features.brain.llm.generate", mock.AsyncMock(return_value={})):
            self.assertIn("non sono riuscito", self.say("spiegami le frazioni alla lavagna"))

    def test_atena_looks_at_what_the_user_wrote_and_checks_it(self):
        self.say("apri la lavagna")
        self.assertIn("non ho ancora visto", self.say("controlla cosa ho scritto"))
        self.board.set_snapshot(JPEG)
        seen = {}

        async def look(jpeg, prompt, **kw):
            seen.update(jpeg=jpeg, prompt=prompt)
            return "Hai scritto 2+2=5: è sbagliato, fa 4.", "modello"
        with mock.patch("features.brain.sight.look", look):
            reply = self.say("controlla cosa ho scritto")
        self.assertIn("sbagliato", reply)
        self.assertEqual(seen["jpeg"], JPEG)
        self.assertIn("insegnante", seen["prompt"])
        self.assertEqual(self.board.says[:11], "Hai scritto")
        self.board.snapshot_at -= service.FRESH + 5
        self.assertIn("non ho ancora visto", self.say("controlla cosa ho scritto"))

    def test_the_whole_feature_can_be_switched_off(self):
        with mock.patch.dict("os.environ", {"ATENA_WHITEBOARD": "0"}):
            with mock.patch.object(commands, "env_get", lambda k, d="": "0"):
                with self.assertRaises(LookupError):
                    self.say("apri la lavagna")


class EndpointTest(Base):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(api.public_routes)
        patcher = mock.patch.object(api, "require_display", lambda request, message="": None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.web = TestClient(app)

    def test_the_display_reads_draws_types_undoes_and_clears(self):
        first = self.web.get("/api/board").json()
        self.assertEqual((first["width"], first["height"], first["items"]), (board_module.WIDTH, board_module.HEIGHT, []))
        self.assertEqual(self.web.get(f"/api/board?rev={first['rev']}").json(), {"rev": first["rev"], "same": True})
        self.assertEqual(self.web.post("/api/board/stroke", json={"points": [[1, 1], [20, 20]], "color": "#ff0000", "width": 8}).status_code, 200)
        self.assertEqual(self.web.post("/api/board/stroke", json={"points": [], "color": "#ff0000"}).status_code, 400)
        self.assertEqual(self.web.post("/api/board/text", json={"text": "ciao", "x": 100, "y": 100}).status_code, 200)
        view = self.web.get("/api/board").json()
        self.assertEqual([i["by"] for i in view["items"]], ["user", "user"])
        self.assertEqual(view["items"][0]["color"], "#ff0000")
        self.assertTrue(self.web.post("/api/board/undo", json={}).json()["undone"])
        self.assertEqual(self.web.post("/api/board/clear", json={}).json()["cleared"], 1)
        self.assertEqual(self.web.get("/api/board").json()["items"], [])

    def test_snapshots_and_bad_bodies_are_checked(self):
        good = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
        self.assertEqual(self.web.post("/api/board/snapshot", json={"image": good}).status_code, 200)
        self.assertEqual(self.board.snapshot, JPEG)
        self.assertEqual(self.web.post("/api/board/snapshot", json={"image": "data:image/jpeg;base64,####"}).status_code, 400)
        self.assertEqual(self.web.post("/api/board/snapshot", json={"image": base64.b64encode(b"non jpeg").decode()}).status_code, 400)
        self.assertEqual(self.web.post("/api/board/stroke", content="{rotto").status_code, 400)
        self.assertEqual(self.web.post("/api/board/stroke", content=b"x" * (api.MAX_BODY + 1)).status_code, 413)

    def test_math_ocr_and_collaboration(self):
        items = [{"type": "text", "by": "user", "text": "2 + 2 =", "x": 100, "y": 100, "size": 40}]
        res = ocr.recognize_math(items)
        self.assertIsNotNone(res)
        self.assertEqual(res["result"], "4")
        self.assertIn("4", res["speech"])
        self.assertEqual(self.web.post("/api/board/text", json={"text": "3 + 5 =", "x": 100, "y": 100}).status_code, 200)
        view = self.web.get("/api/board").json()
        self.assertTrue(any(it.get("by") == "atena" and "8" in it.get("text", "") for it in view["items"]))


class AccessTest(Base):
    def test_other_computers_without_a_session_are_refused(self):
        app = FastAPI()
        app.include_router(api.public_routes)
        web = TestClient(app)
        self.assertEqual(web.get("/api/board").status_code, 401)
        self.assertEqual(web.post("/api/board/clear", json={}).status_code, 401)
        self.assertEqual(web.post("/api/board/stroke", json={"points": [[1, 1]]}).status_code, 401)
        self.assertEqual(self.board.items, [])


class PrecedenceTest(Base):
    def handle(self, text: str) -> dict:
        from features.chat import assistant
        from features.home_assistant.home import brain

        async def greedy_home(said: str):
            if "apri" in said:
                return "Non so fare questa operazione con Ingresso Apri la porta.", {"mode": "face"}, "casa"
            return None

        async def core(_):
            return {"speech_output": "risposta del modello"}
        with mock.patch.object(brain, "handle", greedy_home):
            return asyncio.run(assistant.handle(text, core, {"lang": "it"}))

    def test_the_whiteboard_wins_over_a_home_device_with_a_similar_name(self):
        out = self.handle("apri la lavagna a tutto schermo")
        self.assertEqual(out["intent"], "whiteboard")
        self.assertIn("lavagna", out["reply"])
        self.assertTrue(desk.instances["lavagna"]["fullscreen"])

    def test_real_home_requests_still_reach_the_home_module(self):
        out = self.handle("apri la porta")
        self.assertEqual(out["intent"], "home")
        self.assertIn("Ingresso", out["reply"])
        self.assertEqual(self.handle("apri la lavagna")["intent"], "whiteboard")
        self.handle("apri la lavagna")
        self.assertEqual(self.handle("apri la porta")["intent"], "home")


class ToolTest(Base):
    def run_tool(self, tool_name: str, **args) -> str:
        return asyncio.run(registry.run(tool_name, args))

    def test_the_agent_can_open_write_draw_solve_and_clear(self):
        self.assertIn("tutto schermo", self.run_tool("board_open", fullscreen=True))
        self.assertTrue(desk.instances["lavagna"]["fullscreen"])
        self.run_tool("board_write", text="Triangolo", x=100, y=50, size=60)
        self.run_tool("board_draw", shape="arrow", x1=100, y1=200, x2=600, y2=200)
        self.assertIn("x = 4", self.run_tool("board_solve", expression="2x + 3 = 11"))
        kinds = [i["type"] for i in self.board.items]
        self.assertEqual(kinds[:2], ["text", "arrow"])
        with self.assertRaises(ValueError):
            self.run_tool("board_draw", shape="stella", x1=0, y1=0, x2=1, y2=1)
        with self.assertRaises(ValueError):
            self.run_tool("board_solve", expression="1/0")
        self.assertTrue(registry.needs_confirm("board_clear", {}))
        self.assertIn("pulita", self.run_tool("board_clear"))
        self.assertIn("chiusa", self.run_tool("board_close"))
        self.assertIn("non era aperta", self.run_tool("board_close"))

    def test_the_tools_belong_to_the_whiteboard_agent_and_reach_standard_mcp_tokens(self):
        from features.team import roster
        self.assertEqual(roster.owner("board_solve"), "whiteboard")
        self.assertIn("whiteboard", roster.ids())
        standard = mcp.visible({"id": "t", "label": "x", "risky": False})
        self.assertTrue({"board_open", "board_write", "board_draw", "board_solve", "board_look", "board_close"} <= set(standard))
        self.assertNotIn("board_clear", standard)


class AdvancedTeacherAndPrinterTest(Base):
    def test_multi_page_lifecycle(self):
        self.assertEqual(len(self.board.pages), 1)
        self.assertEqual(self.board.page_index, 0)
        self.board.text("Pagina 1")
        self.assertEqual(len(self.board.items), 1)

        p2 = self.board.add_page()
        self.assertEqual(p2, 1)
        self.assertEqual(self.board.page_index, 1)
        self.assertEqual(len(self.board.items), 0)
        self.board.text("Pagina 2")
        self.assertEqual(len(self.board.items), 1)

        self.board.switch_page(0)
        self.assertEqual(self.board.page_index, 0)
        self.assertEqual(self.board.items[0]["text"], "Pagina 1")

        self.board.next_page()
        self.assertEqual(self.board.page_index, 1)
        self.assertEqual(self.board.items[0]["text"], "Pagina 2")

        self.board.prev_page()
        self.assertEqual(self.board.page_index, 0)

        self.board.delete_page(1)
        self.assertEqual(len(self.board.pages), 1)
        self.assertEqual(self.board.page_index, 0)

    def test_ai_toggle(self):
        self.assertTrue(self.board.ai_enabled)
        state = self.board.toggle_ai()
        self.assertFalse(state)
        self.assertFalse(self.board.ai_enabled)
        state = self.board.toggle_ai(True)
        self.assertTrue(state)
        self.assertTrue(self.board.ai_enabled)

    def test_teacher_error_detection_and_dual_methods(self):
        from features.whiteboard import teacher
        err = teacher.detect_student_error("2 + 2 = 5")
        self.assertIsNotNone(err)
        self.assertTrue(err["has_error"])
        self.assertEqual(err["claimed"], "5")
        self.assertEqual(err["expected"], "4")

        res = teacher.teach("2 + 2 = 5", 100, 100)
        self.assertTrue(res["error_detected"])
        self.assertEqual(res["correction"], "4")
        self.assertEqual(res["perfect"], "")

        has_underline = any(i.get("type") == "stroke" and i.get("color") == "#ff4d6a" for i in self.board.items)
        has_hint = any(i.get("type") == "text" and i.get("color") == "#ffd166" for i in self.board.items)
        self.assertTrue(has_underline)
        self.assertTrue(has_hint)

    def test_teacher_university_level_math(self):
        from features.whiteboard import teacher
        d_res = teacher.teach("derivata di x^3 + 2*x")
        self.assertFalse(d_res["error_detected"])
        self.assertIn("3*x**2 + 2", d_res["result"])
        self.assertIn("esponente", d_res["perfect"])

        i_res = teacher.teach("integrale di 3*x^2")
        self.assertFalse(i_res["error_detected"])
        self.assertIn("x**3", i_res["result"])

        l_res = teacher.teach("limite per x -> 0 sin(x)/x")
        self.assertFalse(l_res["error_detected"])
        self.assertEqual(l_res["result"], "1")

    def test_pdf_exporter(self):
        from features.whiteboard.pdf_exporter import export_pages_to_pdf
        pages = [
            {"items": [{"type": "text", "text": "Lezione 1", "x": 50, "y": 50, "size": 36, "color": "#29e0ff"}]},
            {"items": [{"type": "stroke", "points": [[10, 10], [50, 50]], "color": "#f4f4f0", "width": 4}]}
        ]
        pdf_bytes = export_pages_to_pdf(pages)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_universal_printer_manager(self):
        from features.whiteboard.printer import printer_manager
        printers = printer_manager.list_printers()
        self.assertGreaterEqual(len(printers), 3)
        types = {p["type"] for p in printers}
        self.assertIn("virtual_pdf", types)
        self.assertIn("engraver", types)
        self.assertIn("3d", types)

        gcode_laser = printer_manager.generate_grbl_gcode(self.board.pages, power=350, feed=1000)
        self.assertIn("G21", gcode_laser)
        self.assertIn("M5", gcode_laser)

        gcode_3d = printer_manager.generate_3d_gcode(self.board.pages)
        self.assertIn("G28", gcode_3d)

        job = printer_manager.print_job("pdf_export")
        self.assertEqual(job["status"], "ok")


if __name__ == "__main__":
    unittest.main()

