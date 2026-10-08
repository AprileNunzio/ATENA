import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

def translate_str(text: str, source: str = "it", target: str = "fr") -> str:
    if not text or not str(text).strip():
        return text
    s = str(text)
    if len(s) > 4000:
        return s
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl="
        + source
        + "&tl="
        + target
        + "&dt=t&q="
        + urllib.parse.quote(s)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return "".join([part[0] for part in data[0] if part[0]])
        except Exception:
            time.sleep(0.5)
    return s

def translate_structure(obj, source: str = "it", target: str = "fr"):
    if isinstance(obj, dict):
        return {k: translate_structure(v, source, target) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [translate_structure(v, source, target) for v in obj]
    elif isinstance(obj, str):
        return translate_str(obj, source, target)
    return obj

def process_file(it_path: Path, target_lang: str):
    target_path = it_path.parent / f"{target_lang}.json"
    if target_path.exists():
        return target_path, "skipped"
    try:
        content = json.loads(it_path.read_text(encoding="utf-8"))
        translated = translate_structure(content, source="it", target=target_lang)
        target_path.write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")
        return target_path, "created"
    except Exception as e:
        return target_path, f"error: {e}"

def generate_translations(target_lang: str = "fr"):
    root = Path(__file__).resolve().parent.parent.parent.parent
    it_files = [p for p in root.rglob("it.json") if p.parent.name == "language"]
    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(process_file, p, target_lang) for p in it_files]
        for f in futures:
            results.append(f.result())
    return results

if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "fr"
    res = generate_translations(lang)
    created = [p for p, status in res if status == "created"]
    print(f"Generated {len(created)} language files for '{lang}'.")
