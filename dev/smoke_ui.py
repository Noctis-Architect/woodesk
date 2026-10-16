"""Headless smoke test: runs the real UI against dev/fake_store.py and saves screenshots."""
import os
import sys
import tempfile
import threading
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["WOODESK_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn  # noqa: E402

from dev.fake_store import app as fake  # noqa: E402

server = uvicorn.Server(uvicorn.Config(fake, host="127.0.0.1", port=8099, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
time.sleep(1.2)

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from app.core import secrets  # noqa: E402
from app.core.config import Site, cfg  # noqa: E402

cfg.language = sys.argv[1] if len(sys.argv) > 1 else "fa"
cfg.theme = sys.argv[2] if len(sys.argv) > 2 else "light"
s = Site(id="demo", name="Demo Store", url="http://127.0.0.1:8099", wp_user="admin", use_woo_keys=True)
cfg.add_site(s)
secrets.set("site:demo:wp_password", "x")
secrets.set("site:demo:ck", "ck_x")
secrets.set("site:demo:cs", "cs_x")
cfg.ai.base_url = "http://127.0.0.1:8099/v1"
cfg.ai.model = "fake-model-1"
cfg.ai.output_language = "fa"
cfg.telemetry_notice_shown = True
cfg.save()

from app.main import create_app  # noqa: E402

app, ctx, win = create_app([])
win.show()


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.02)


out = os.environ.get("SHOTS", "/tmp/shots")
os.makedirs(out, exist_ok=True)
results = {}
pump(1.5)
win.grab().save(f"{out}/dashboard.png")
win.goto("products"); pump(2.5)
pp = win.pages["products"]
results["product_rows"] = pp.table.rowCount()
win.grab().save(f"{out}/products.png")
win.goto("posts"); pump(1.5)
results["post_rows"] = win.pages["posts"].table.rowCount()
win.grab().save(f"{out}/posts.png")
win.goto("media"); pump(2)
results["media_items"] = win.pages["media"].grid.count()
win.grab().save(f"{out}/media.png")
win.goto("settings"); pump(0.5)
win.grab().save(f"{out}/settings.png")

# product editor
from app.ui.pages.product_editor import ProductEditor  # noqa: E402

ed = ProductEditor(ctx, pp.rows[0], win)
ed.show(); pump(1.5)
ed.grab().save(f"{out}/editor.png")
ed.tabs.setCurrentIndex(4); pump(0.2)
ed.name.setText("Edited by smoke test")
ed.tags.setText("new, brandnew")
ed.save(); pump(2)
from dev.fake_store import PRODUCTS  # noqa: E402

edited = next(p for p in PRODUCTS if p["id"] == pp.rows[0]["id"])
results["edit_saved"] = edited["name"] == "Edited by smoke test"
results["tag_created"] = any(t["name"] == "brandnew" for t in edited["tags"])
ed.close()

# variable product + generate variations
var = next(r for r in pp.rows if r["type"] == "variable") if any(r["type"] == "variable" for r in pp.rows) else None
if var:
    ed2 = ProductEditor(ctx, var, win)
    ed2.show(); pump(1.5)
    results["variations_loaded"] = ed2.var_table.rowCount()
    ed2.attr_table.item(0, 1).setText("Red, Blue, Green")
    ed2.generate_variations(); pump(2)
    results["variations_after_generate"] = ed2.var_table.rowCount()
    ed2.close()

# new post via editor
from app.ui.pages.posts import PostEditor  # noqa: E402

pe = PostEditor(ctx, None, win)
pe.show(); pump(1)
pe.title.setText("Hello from smoke test")
pe.content.set_text("<p>hi</p>")
pe.tags.setText("x1")
pe.save(); pump(1.5)
from dev.fake_store import POSTS  # noqa: E402

results["post_created"] = any(p["title"]["raw"] == "Hello from smoke test" for p in POSTS)
pe.close()

# bulk price
pp.load(1); pump(1.5)
from PySide6.QtCore import Qt; pp.table.item(0, 0).setCheckState(Qt.Checked)
pp._batch(update=[{"id": pp.rows[0]["id"], "status": "draft"}]); pump(1.5)
results["bulk_status"] = next(p for p in PRODUCTS if p["id"] == pp.rows[0]["id"])["status"] == "draft"

print(results)
sys.stdout.flush()
ok = all(bool(v) for v in results.values())
os._exit(0 if ok else 1)
