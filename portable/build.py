"""현재 화면과 모듈 목록 및 새 시드를 인터넷이 필요 없는 파일로 묶습니다."""

import base64
import json
from pathlib import Path
import sqlite3
import tempfile

from adapters import EVENT_ROUTES
from server.app import ROOT, create_app


def inline_script(source):
    return source.replace("</script", "<\\/script")


def build(output=None):
    output = Path(output or ROOT / "IBCM.html")
    folder = Path(__file__).parent
    with tempfile.TemporaryDirectory(prefix="ibcm-portable-seed-") as temporary:
        database = Path(temporary) / "seed.sqlite3"
        app = create_app(database, testing=True)
        detail = app.test_client().get("/api/projects/1").get_json()
        with sqlite3.connect(database) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("PRAGMA journal_mode=DELETE")
        config = {
            "wasmBase64": base64.b64encode((folder / "vendor/sql-wasm.wasm").read_bytes()).decode(),
            "databaseBase64": base64.b64encode(database.read_bytes()).decode(),
            "modules": detail["modules"],
            "stages": detail["stages"],
            "routes": EVENT_ROUTES,
        }
    html = (ROOT / "public/index.html").read_text(encoding="utf-8")
    css = (ROOT / "public/styles.css").read_text(encoding="utf-8")
    js = (ROOT / "public/app.js").read_text(encoding="utf-8")
    store_js = (ROOT / "public/store.js").read_text(encoding="utf-8")
    runtime = (folder / "runtime.js").read_text(encoding="utf-8")
    sql = (folder / "vendor/sql-wasm.js").read_text(encoding="utf-8")
    license_text = (folder / "vendor/LICENSE").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/styles.css">', f"<style>{css}</style>")
    html = html.replace('    <script src="/app.js" defer></script>\n', "")
    html = html.replace('    <script src="/store.js" defer></script>\n', "")
    html = html.replace('<meta charset="utf-8">', '''<meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'">''')
    html = html.replace('class="brand" href="/"', 'class="brand" href="#main"')
    scripts = "\n".join(f"<script>{inline_script(source)}</script>" for source in (
        "/* sql.js 1.14.1 license\n" + license_text.replace("*/", "* /") + "\n*/\n" + sql,
        "window.IBCM_PORTABLE = " + json.dumps(config, ensure_ascii=False) + ";",
        runtime,
        store_js,
        js,
    ))
    html = html.replace("</body>", scripts + "\n</body>")
    output.write_text(html, encoding="utf-8")
    print(f"단일 파일 생성 완료: {output} ({output.stat().st_size:,} 바이트)")
    return output


if __name__ == "__main__":
    standalone = build()
    pages = ROOT / "docs"
    pages.mkdir(exist_ok=True)
    (pages / "index.html").write_bytes(standalone.read_bytes())
    (pages / ".nojekyll").write_text("", encoding="utf-8")
    print(f"GitHub Pages 파일 준비 완료: {pages / 'index.html'}")
