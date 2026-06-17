from app.agents.base_agent import BaseAgent
from app.projects.project_workspace import ProjectWorkspaceManager
from app.projects.schemas import ProjectFileWriteResult
from app.workspace.file_writer import WorkspaceFileWriter
from app.workspace.schemas import FileManifestEntry


class FileBuilderAgent(BaseAgent):
    def build_project_greek_yogurt_site(self, project_id: str, run_id: str, command: str) -> list[ProjectFileWriteResult]:
        writer = ProjectWorkspaceManager()
        files = self._project_files(include_status_page=self._needs_status_page(command))
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

    def _needs_status_page(self, command: str) -> bool:
        normalized = command.lower()
        return "status" in normalized or "continue" in normalized

    def _summary_for(self, path: str, command: str) -> str:
        if "status" in path:
            return "Order status tracking data for the Greek yogurt website."
        if path.endswith("app.py") and self._needs_status_page(command):
            return "Standard-library Greek yogurt order website backend with order intake and status page routes."
        if path.endswith("index.html") and self._needs_status_page(command):
            return "Greek yogurt homepage and order form with a link to the order status page."
        if path.endswith("status.html"):
            return "Simple order status page for manually reviewed Greek yogurt orders."
        return f"Persistent Greek yogurt website project file {path}."

    def _project_files(self, *, include_status_page: bool) -> dict[str, str]:
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
            "website/templates/index.html": self._index_html(include_status_page=include_status_page),
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

    def _index_html(self, *, include_status_page: bool) -> str:
        status_link = "<p><a href=\"/status?order_id=GY-1001\">Check sample order status</a></p>" if include_status_page else ""
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
      .product, form {{ background: white; border: 1px solid #d9e2dc; padding: 16px; border-radius: 8px; }}
      label {{ display: block; margin-top: 12px; font-weight: 700; }}
      input, select, button {{ width: 100%; padding: 10px; margin-top: 6px; box-sizing: border-box; }}
      button {{ background: #2f855a; color: white; border: 0; border-radius: 6px; cursor: pointer; }}
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
