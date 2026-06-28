#!/usr/bin/env python3
"""Простий статичний сервер для перегляду демо-дизайну на мобільних девайсах по LAN.

Роздає папку, де лежить цей файл (design/), на 0.0.0.0:PORT.
Друкує локальні IP-адреси, щоб відкрити з телефону в тій самій Wi-Fi.

Запуск: python3 serve.py [PORT]   (PORT за замовч. 8000)
Або через VS Code: Run and Debug → "Demo: serve design (LAN)".
"""

import http.server
import os
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
DIR = os.path.dirname(os.path.abspath(__file__))


def lan_ips() -> list[str]:
    """Усі IPv4-адреси хоста (без loopback)."""
    ips: set[str] = set()
    try:
        # надійний спосіб дізнатись «вихідний» інтерфейс
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except socket.gaierror:
        pass
    return sorted(ips)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def end_headers(self):
        # завжди свіжа версія — зручно під час правок дизайну
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write("  %s - %s\n" % (self.address_string(), fmt % args))


def main():
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    files = sorted(f for f in os.listdir(DIR) if f.endswith(".html"))

    print(f"\n  Serving {DIR}")
    print(f"  Port    {PORT}\n")
    print("  Open on this machine:")
    print(f"    http://localhost:{PORT}/")
    print("\n  Open on phone/tablet (same Wi-Fi):")
    for ip in lan_ips():
        print(f"    http://{ip}:{PORT}/")
    if files:
        print("\n  Pages:")
        for f in files:
            print(f"    /{f}")
    print("\n  Ctrl+C to stop.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        httpd.server_close()


if __name__ == "__main__":
    main()
