"""Tiny test page for task 0.2.

It proves that the Mac Mini can be reached from the internet through
Cloudflare Tunnel. It uses only Python's built-in tools (nothing to install).
The real bot (task 1.1) will replace it.

Run it by hand:   python3 server/hello.py
Then open:        http://localhost:8000
"""

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 127.0.0.1 = "this computer only". Other devices on the home Wi-Fi can't reach
# it directly; only the Cloudflare Tunnel (running on the same Mac) can.
HOST = "127.0.0.1"
PORT = 8000

PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pashut Book</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; text-align: center;
         padding: 3em 1em; background: #faf7f2; color: #333; }}
  h1 {{ font-size: 2em; }}
</style>
</head>
<body>
<h1>✅ השרת של פשוט בוק עובד</h1>
<p>הדף הזה מגיע מה-Mac Mini.</p>
<p>{time}</p>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body, content_type = b"ok", "text/plain; charset=utf-8"
        else:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            body = PAGE.format(time=now).encode("utf-8")
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"Test page running at http://localhost:{PORT} (press Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
