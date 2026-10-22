from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/v1/responses" or self.headers.get("Authorization") != "Bearer e2e-key":
            self.send_error(401)
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if (
            body.get("store") is not False
            or body.get("text", {}).get("format", {}).get("type") != "json_schema"
        ):
            self.send_error(422)
            return
        analysis = {
            "document_type": "nota di collaudo",
            "summary": "Documento privato usato per verificare Jarvis.",
            "facts": [
                {
                    "label": "contenuto",
                    "value": "collaudo Jarvis",
                    "source_text": "Jarvis private E2E document",
                }
            ],
            "deadlines": [],
            "suggested_actions": ["Archiviare l'esito del collaudo"],
            "missing_information": [],
        }
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(analysis)}],
                }
            ]
        }
        encoded = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()  # noqa: S104
