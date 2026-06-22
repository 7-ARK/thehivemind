from app.agents.base_agent import BaseAgent
from app.projects.project_workspace import ProjectWorkspaceManager
from app.projects.schemas import ProjectFileWriteResult
from app.workspace.file_writer import WorkspaceFileWriter
from app.workspace.schemas import FileManifestEntry


class FileBuilderAgent(BaseAgent):
    def build_project_greek_yogurt_homepage_copy_update(
        self,
        project_id: str,
        run_id: str,
        command: str,
        memory_themes: list[str] | None = None,
    ) -> list[ProjectFileWriteResult]:
        writer = ProjectWorkspaceManager()
        existing_paths = {item.path for item in writer.get_project_manifest(project_id).files}
        include_status_page = "website/templates/status.html" in existing_paths or "website/data/order_statuses.json" in existing_paths
        files = {
            "website/templates/index.html": self._homepage_copy_index_html(
                include_status_page=include_status_page,
                memory_themes=memory_themes or [],
            ),
            "website/data/faqs.json": self._homepage_copy_faqs_json(),
        }
        entries = []
        for path, content in files.items():
            entries.append(
                writer.write_project_file(
                    project_id=project_id,
                    relative_path=path,
                    content=content,
                    agent_name=self.name,
                    run_id=run_id,
                    summary=self._summary_for(path, command),
                )
            )
        return entries

    def build_project_greek_yogurt_site(self, project_id: str, run_id: str, command: str) -> list[ProjectFileWriteResult]:
        writer = ProjectWorkspaceManager()
        existing_paths = {item.path for item in writer.get_project_manifest(project_id).files}
        files = self._project_files(
            include_status_page=self._needs_status_page(command, existing_paths),
            include_faq_section=self._needs_faq_section(command, existing_paths),
        )
        entries = []
        for path, content in files.items():
            entries.append(
                writer.write_project_file(
                    project_id=project_id,
                    relative_path=path,
                    content=content,
                    agent_name=self.name,
                    run_id=run_id,
                    summary=self._summary_for(path, command),
                )
            )
        return entries

    def _needs_status_page(self, command: str, existing_paths: set[str] | None = None) -> bool:
        normalized = command.lower()
        existing = existing_paths or set()
        return "status" in normalized or "continue" in normalized or "website/templates/status.html" in existing or "website/data/order_statuses.json" in existing

    def _needs_faq_section(self, command: str, existing_paths: set[str] | None = None) -> bool:
        normalized = command.lower()
        existing = existing_paths or set()
        return "faq" in normalized or "frequently asked" in normalized or "website/data/faqs.json" in existing

    def _summary_for(self, path: str, command: str) -> str:
        if "status" in path:
            return "Order status tracking data for the Greek yogurt website."
        if path.endswith("app.py") and self._needs_status_page(command):
            return "Standard-library Greek yogurt order website backend with order intake and status page routes."
        if path.endswith("index.html") and self._needs_faq_section(command):
            return "Greek yogurt homepage with a small FAQ section for ordering, delivery, and manual approval."
        if path.endswith("index.html") and self._needs_status_page(command):
            return "Greek yogurt homepage and order form with a link to the order status page."
        if path.endswith("faqs.json"):
            return "FAQ content for the Greek yogurt website."
        if path.endswith("status.html"):
            return "Simple order status page for manually reviewed Greek yogurt orders."
        return f"Persistent Greek yogurt website project file {path}."

    def _project_files(self, *, include_status_page: bool, include_faq_section: bool = False) -> dict[str, str]:
        files = {
            "website/README.md": """# Greek Yogurt Order Website Prototype

This is a safe local prototype for a Greek yogurt order flow. It does not process real payments, send messages, or run a production server.

## Files

- `app.py`: standard-library Python HTTP prototype.
- `templates/index.html`: homepage and order form structure.
- `data/sample_orders.json`: fake sample order data.
- `requirements.txt`: intentionally empty because the prototype uses Python standard library only.

## Run Manually

```bash
python app.py
```

Then open `http://127.0.0.1:8080`.

## Next Steps

- Replace fake data with a real database.
- Add admin approval screens.
- Keep FAQ answers aligned with final pricing, delivery radius, and storage guidance.
- Add WhatsApp handoff copy.
- Verify all pricing, delivery, nutrition, and legal claims before public use.
""",
            "website/app.py": self._app_py(include_status_page=include_status_page),
            "website/requirements.txt": "# Standard-library prototype. No packages required.\n",
            "website/data/sample_orders.json": """[
  {
    "order_id": "GY-1001",
    "name": "Ayesha",
    "flavor": "Classic Honey",
    "quantity": 2,
    "status": "sample_pending_manual_approval"
  },
  {
    "order_id": "GY-1002",
    "name": "Hamza",
    "flavor": "Berry Crunch",
    "quantity": 1,
    "status": "sample_follow_up"
  }
]
""",
            "website/templates/index.html": self._index_html(
                include_status_page=include_status_page,
                include_faq_section=include_faq_section,
            ),
        }
        if include_status_page:
            files["website/templates/status.html"] = self._status_html()
            files["website/data/order_statuses.json"] = """[
  {
    "order_id": "GY-1001",
    "status": "pending_manual_approval",
    "message": "Your founder-batch order is waiting for manual confirmation."
  },
  {
    "order_id": "GY-1002",
    "status": "follow_up",
    "message": "We need to confirm your delivery slot before preparing the batch."
  }
]
"""
        if include_faq_section:
            files["website/data/faqs.json"] = """[
  {
    "question": "Can I place a real order from this prototype?",
    "answer": "No. This local prototype only demonstrates the flow; every order needs manual human confirmation."
  },
  {
    "question": "Are prices and delivery areas final?",
    "answer": "No. Pricing, delivery radius, and product claims must be approved before public use."
  },
  {
    "question": "Does the site process payments?",
    "answer": "No. Payments, WhatsApp messages, and external actions are intentionally not connected."
  }
]
"""
        return files

    def _app_py(self, *, include_status_page: bool) -> str:
        status_routes = """
    def _status_payload(self, order_id):
        statuses_path = ROOT / "data" / "order_statuses.json"
        if not statuses_path.exists():
            return {"order_id": order_id, "status": "unknown", "message": "Status tracking has not been configured yet."}
        statuses = json.loads(statuses_path.read_text(encoding="utf-8"))
        for item in statuses:
            if item.get("order_id", "").lower() == order_id.lower():
                return item
        return {"order_id": order_id, "status": "not_found", "message": "No matching demo order was found."}
""" if include_status_page else ""
        status_get = """
        if self.path.startswith("/status"):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = parse_qs(query)
            order_id = params.get("order_id", ["GY-1001"])[0]
            template = (ROOT / "templates" / "status.html").read_text(encoding="utf-8")
            payload = self._status_payload(order_id)
            html = template.replace("{{ order_id }}", payload["order_id"]).replace("{{ status }}", payload["status"]).replace("{{ message }}", payload["message"])
            self._send_html(html)
            return
""" if include_status_page else ""
        status_append = """
        statuses_path = ROOT / "data" / "order_statuses.json"
        statuses = json.loads(statuses_path.read_text(encoding="utf-8")) if statuses_path.exists() else []
        statuses.append({
            "order_id": order_id,
            "status": "pending_manual_approval",
            "message": "Your order was received and is waiting for manual confirmation."
        })
        statuses_path.write_text(json.dumps(statuses, indent=2), encoding="utf-8")
""" if include_status_page else ""
        return f"""from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs
import json


ROOT = Path(__file__).parent
TEMPLATE = ROOT / "templates" / "index.html"
ORDERS = ROOT / "data" / "sample_orders.json"


class GreekYogurtHandler(BaseHTTPRequestHandler):
    def do_GET(self):
{status_get}        if self.path not in {{"/", "/index.html"}}:
            self.send_error(404, "Not found")
            return
        html = TEMPLATE.read_text(encoding="utf-8")
        self._send_html(html)

    def do_POST(self):
        if self.path != "/order":
            self.send_error(404, "Not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        form = {{key: values[0] for key, values in parse_qs(payload).items()}}
        orders = json.loads(ORDERS.read_text(encoding="utf-8"))
        order_id = f"GY-{{1000 + len(orders) + 1}}"
        orders.append({{
            "order_id": order_id,
            "name": form.get("name", "Demo Customer"),
            "flavor": form.get("flavor", "Classic Honey"),
            "quantity": int(form.get("quantity", "1") or 1),
            "status": "pending_manual_approval",
        }})
        ORDERS.write_text(json.dumps(orders, indent=2), encoding="utf-8")
{status_append}        self._send_html(f"<h1>Order received for manual approval</h1><p>Demo order ID: {{order_id}}</p><p><a href='/'>Back</a></p>")
{status_routes}
    def _send_html(self, body):
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    server = HTTPServer(("127.0.0.1", 8080), GreekYogurtHandler)
    print("Prototype server at http://127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
"""

    def _index_html(self, *, include_status_page: bool, include_faq_section: bool = False) -> str:
        status_link = "<p><a href=\"/status?order_id=GY-1001\">Check sample order status</a></p>" if include_status_page else ""
        faq_section = """
      <section class="faq">
        <h2>FAQ</h2>
        <details open><summary>Can I place a real order from this prototype?</summary><p>No. Orders stay manual and must be confirmed by a human.</p></details>
        <details><summary>Are prices and delivery areas final?</summary><p>No. Pricing, delivery radius, and product claims need approval before launch.</p></details>
        <details><summary>Does the site process payments?</summary><p>No. Payments, WhatsApp messages, and external actions are intentionally not connected.</p></details>
      </section>
""" if include_faq_section else ""
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Thick Spoon Greek Yogurt</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 0; background: #f7faf7; color: #1f2933; }}
      main {{ max-width: 880px; margin: 0 auto; padding: 40px 20px; }}
      .hero {{ background: white; border: 1px solid #d9e2dc; padding: 28px; border-radius: 8px; }}
      .products {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
      .product, form, .faq {{ background: white; border: 1px solid #d9e2dc; padding: 16px; border-radius: 8px; }}
      label {{ display: block; margin-top: 12px; font-weight: 700; }}
      input, select, button {{ width: 100%; padding: 10px; margin-top: 6px; box-sizing: border-box; }}
      button {{ background: #2f855a; color: white; border: 0; border-radius: 6px; cursor: pointer; }}
      details {{ margin-top: 10px; }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <h1>Thick Spoon Greek Yogurt</h1>
        <p>Founder-batch Greek yogurt cups for breakfast, dessert, and post-workout cravings in Pakistan.</p>
        <p><strong>Note:</strong> Orders are manually reviewed before confirmation.</p>
        {status_link}
      </section>
      <section class="products">
        <article class="product"><h2>Classic Honey</h2><p>Thick yogurt, honey drizzle, toasted nuts.</p></article>
        <article class="product"><h2>Berry Crunch</h2><p>Berry compote, granola, chilled yogurt.</p></article>
        <article class="product"><h2>Desi Mango</h2><p>Mango layer, plain yogurt, cardamom hint.</p></article>
      </section>
{faq_section}
      <form method="post" action="/order">
        <h2>Request an Order</h2>
        <label>Name<input name="name" required /></label>
        <label>Flavor
          <select name="flavor">
            <option>Classic Honey</option>
            <option>Berry Crunch</option>
            <option>Desi Mango</option>
          </select>
        </label>
        <label>Quantity<input name="quantity" type="number" min="1" value="1" /></label>
        <button type="submit">Send for Manual Approval</button>
      </form>
    </main>
  </body>
</html>
"""

    def _status_html(self) -> str:
        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Order Status | Thick Spoon Greek Yogurt</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 0; background: #f7faf7; color: #1f2933; }
      main { max-width: 720px; margin: 0 auto; padding: 40px 20px; }
      section { background: white; border: 1px solid #d9e2dc; padding: 24px; border-radius: 8px; }
      code { background: #edf5ef; padding: 2px 5px; border-radius: 4px; }
    </style>
  </head>
  <body>
    <main>
      <section>
        <h1>Order Status</h1>
        <p>Order <code>{{ order_id }}</code></p>
        <p><strong>Status:</strong> {{ status }}</p>
        <p>{{ message }}</p>
        <p><a href="/">Back to order form</a></p>
      </section>
    </main>
  </body>
</html>
"""

    def _homepage_copy_index_html(self, *, include_status_page: bool, memory_themes: list[str]) -> str:
        status_link = "<p><a href=\"/status?order_id=GY-1001\">Check sample order status</a></p>" if include_status_page else ""
        theme_note = " ".join(memory_themes[:2]) or "The copy leans into thick texture, high protein, clean ingredients, and founder-batch freshness."
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Thick Spoon Greek Yogurt</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 0; background: #f7faf7; color: #1f2933; }}
      main {{ max-width: 880px; margin: 0 auto; padding: 40px 20px; }}
      .hero {{ background: white; border: 1px solid #d9e2dc; padding: 28px; border-radius: 8px; }}
      .products {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
      .product, form, .faq {{ background: white; border: 1px solid #d9e2dc; padding: 16px; border-radius: 8px; }}
      label {{ display: block; margin-top: 12px; font-weight: 700; }}
      input, select, button {{ width: 100%; padding: 10px; margin-top: 6px; box-sizing: border-box; }}
      button {{ background: #2f855a; color: white; border: 0; border-radius: 6px; cursor: pointer; }}
      details {{ margin-top: 10px; }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <h1>Thick Spoon Greek Yogurt</h1>
        <p>Small-batch Greek yogurt cups built around thick texture, protein-forward positioning, and clean-label flavors.</p>
        <p>Inspired by competitor memory around Chobani, Oikos, FAGE, and high-protein premium yogurt positioning.</p>
        <p><strong>Memory note:</strong> {theme_note}</p>
        <p><strong>Safety note:</strong> Orders, prices, delivery areas, and nutrition claims still need human approval.</p>
        {status_link}
      </section>
      <section class="products">
        <article class="product"><h2>Classic Honey</h2><p>Thick plain yogurt with a honey finish for simple daily breakfasts.</p></article>
        <article class="product"><h2>Berry Crunch</h2><p>Fruit, granola, and chilled yogurt for a snack that feels fresh and filling.</p></article>
        <article class="product"><h2>Desi Mango</h2><p>Mango, plain Greek-style yogurt, and a light cardamom note for local taste.</p></article>
      </section>
      <section class="faq">
        <h2>FAQ</h2>
        <details open><summary>Can I place a real order from this prototype?</summary><p>No. Orders stay manual and must be confirmed by a human.</p></details>
        <details><summary>Are the health and nutrition claims final?</summary><p>No. Claims about protein, calories, ingredients, and storage must be verified before public use.</p></details>
        <details><summary>Was new live research used for this copy?</summary><p>No. This update uses previous memory and should not be treated as fresh search.</p></details>
      </section>
      <form method="post" action="/order">
        <h2>Request an Order</h2>
        <label>Name<input name="name" required /></label>
        <label>Flavor
          <select name="flavor">
            <option>Classic Honey</option>
            <option>Berry Crunch</option>
            <option>Desi Mango</option>
          </select>
        </label>
        <label>Quantity<input name="quantity" type="number" min="1" value="1" /></label>
        <button type="submit">Send for Manual Approval</button>
      </form>
    </main>
  </body>
</html>
"""

    def _homepage_copy_faqs_json(self) -> str:
        return """[
  {
    "question": "Can I place a real order from this prototype?",
    "answer": "No. This local prototype only demonstrates the flow; every order needs manual human confirmation."
  },
  {
    "question": "Was new live research used for this copy update?",
    "answer": "No. This copy should be treated as memory-assisted, not fresh live research."
  },
  {
    "question": "Are protein, nutrition, pricing, and delivery claims final?",
    "answer": "No. Product claims, pricing, delivery radius, and storage guidance must be verified before public use."
  }
]
"""

    def build_greek_yogurt_site(self, run_id: str) -> list[FileManifestEntry]:
        writer = WorkspaceFileWriter()
        files = {
            "generated/greek_yogurt_site/README.md": """# Greek Yogurt Order Website Prototype

This is a safe local prototype for a Greek yogurt order flow. It does not process real payments, send messages, or run a production server.

## Files

- `app.py`: standard-library Python HTTP prototype.
- `templates/index.html`: homepage and order form structure.
- `data/sample_orders.json`: fake sample order data.
- `requirements.txt`: intentionally empty because the prototype uses Python standard library only.

## Run Manually

```bash
python app.py
```

Then open `http://127.0.0.1:8080`.

## Next Steps

- Replace fake data with a real database.
- Add admin approval screens.
- Add WhatsApp handoff copy.
- Verify all pricing, delivery, nutrition, and legal claims before public use.
""",
            "generated/greek_yogurt_site/app.py": """from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs
import json


ROOT = Path(__file__).parent
TEMPLATE = ROOT / "templates" / "index.html"
ORDERS = ROOT / "data" / "sample_orders.json"


class GreekYogurtHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/index.html"}:
            self.send_error(404, "Not found")
            return
        html = TEMPLATE.read_text(encoding="utf-8")
        self._send_html(html)

    def do_POST(self):
        if self.path != "/order":
            self.send_error(404, "Not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        form = {key: values[0] for key, values in parse_qs(payload).items()}
        orders = json.loads(ORDERS.read_text(encoding="utf-8"))
        orders.append({
            "name": form.get("name", "Demo Customer"),
            "flavor": form.get("flavor", "Classic Honey"),
            "quantity": int(form.get("quantity", "1") or 1),
            "status": "pending_manual_approval",
        })
        ORDERS.write_text(json.dumps(orders, indent=2), encoding="utf-8")
        self._send_html("<h1>Order received for manual approval</h1><p><a href='/'>Back</a></p>")

    def _send_html(self, body):
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    server = HTTPServer(("127.0.0.1", 8080), GreekYogurtHandler)
    print("Prototype server at http://127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
""",
            "generated/greek_yogurt_site/requirements.txt": "# Standard-library prototype. No packages required.\n",
            "generated/greek_yogurt_site/data/sample_orders.json": """[
  {
    "name": "Ayesha",
    "flavor": "Classic Honey",
    "quantity": 2,
    "status": "sample_pending_manual_approval"
  },
  {
    "name": "Hamza",
    "flavor": "Berry Crunch",
    "quantity": 1,
    "status": "sample_follow_up"
  }
]
""",
            "generated/greek_yogurt_site/templates/index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Thick Spoon Greek Yogurt</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 0; background: #f7faf7; color: #1f2933; }
      main { max-width: 880px; margin: 0 auto; padding: 40px 20px; }
      .hero { background: white; border: 1px solid #d9e2dc; padding: 28px; border-radius: 8px; }
      .products { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }
      .product, form { background: white; border: 1px solid #d9e2dc; padding: 16px; border-radius: 8px; }
      label { display: block; margin-top: 12px; font-weight: 700; }
      input, select, button { width: 100%; padding: 10px; margin-top: 6px; box-sizing: border-box; }
      button { background: #2f855a; color: white; border: 0; border-radius: 6px; cursor: pointer; }
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <h1>Thick Spoon Greek Yogurt</h1>
        <p>Founder-batch Greek yogurt cups for breakfast, dessert, and post-workout cravings in Pakistan.</p>
        <p><strong>Note:</strong> Orders are manually reviewed before confirmation.</p>
      </section>
      <section class="products">
        <article class="product"><h2>Classic Honey</h2><p>Thick yogurt, honey drizzle, toasted nuts.</p></article>
        <article class="product"><h2>Berry Crunch</h2><p>Berry compote, granola, chilled yogurt.</p></article>
        <article class="product"><h2>Desi Mango</h2><p>Mango layer, plain yogurt, cardamom hint.</p></article>
      </section>
      <form method="post" action="/order">
        <h2>Request an Order</h2>
        <label>Name<input name="name" required /></label>
        <label>Flavor
          <select name="flavor">
            <option>Classic Honey</option>
            <option>Berry Crunch</option>
            <option>Desi Mango</option>
          </select>
        </label>
        <label>Quantity<input name="quantity" type="number" min="1" value="1" /></label>
        <button type="submit">Send for Manual Approval</button>
      </form>
    </main>
  </body>
</html>
""",
        }
        entries = []
        for path, content in files.items():
            entries.append(
                writer.write_file(
                    run_id=run_id,
                    relative_path=path,
                    content=content,
                    agent_name=self.name,
                    summary=f"Generated prototype file {path}.",
                )
            )
        return entries
