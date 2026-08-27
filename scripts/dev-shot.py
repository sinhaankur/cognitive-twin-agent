#!/usr/bin/env python3
"""Screenshot a URL via Chrome DevTools Protocol — stdlib only.

Usage: cdp_shot.py URL OUT.png [WAIT_SECONDS] [WIDTH] [HEIGHT]

Launches its own new-headless Chrome (real clock — animations run truly),
navigates, waits WAIT_SECONDS of real time, captures a PNG, exits.
"""
import base64
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def ws_connect(url):
    # ws://host:port/path -> handshake, return socket
    rest = url.split("://", 1)[1]
    hostport, _, path = rest.partition("/")
    host, _, port = hostport.partition(":")
    s = socket.create_connection((host, int(port or 80)), timeout=30)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((
        f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    ).encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError("handshake failed")
        resp += chunk
    if b" 101 " not in resp.split(b"\r\n", 1)[0]:
        raise RuntimeError("no upgrade: " + resp.decode(errors="replace")[:200])
    return s


def ws_send(s, payload: bytes):
    mask = os.urandom(4)
    n = len(payload)
    head = b"\x81"  # FIN + text
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 1 << 16:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(head + mask + masked)


def _recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("connection closed")
        buf += chunk
    return buf


def ws_recv_message(s):
    # reassemble one full (possibly fragmented) message
    parts = []
    while True:
        b1, b2 = _recv_exact(s, 2)
        fin, opcode = b1 & 0x80, b1 & 0x0F
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", _recv_exact(s, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", _recv_exact(s, 8))[0]
        if b2 & 0x80:  # masked (server never masks, but be safe)
            mask = _recv_exact(s, 4)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(_recv_exact(s, n)))
        else:
            data = _recv_exact(s, n)
        if opcode == 8:  # close
            raise RuntimeError("closed by peer")
        if opcode == 9:  # ping -> pong
            ws_send(s, data)
            continue
        parts.append(data)
        if fin:
            return b"".join(parts)


def cdp(s, id_, method, params=None):
    ws_send(s, json.dumps({"id": id_, "method": method,
                           "params": params or {}}).encode())


def cdp_wait(s, id_):
    while True:
        msg = json.loads(ws_recv_message(s))
        if msg.get("id") == id_:
            return msg


def main():
    url, out = sys.argv[1], sys.argv[2]
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
    w = int(sys.argv[4]) if len(sys.argv) > 4 else 1280
    h = int(sys.argv[5]) if len(sys.argv) > 5 else 860
    port = 9333
    headed = os.environ.get("CDP_HEADED") == "1"
    chrome = subprocess.Popen(
        [CHROME] + ([] if headed else ["--headless=new"])
        + [f"--remote-debugging-port={port}",
         f"--window-size={w},{h}", "--no-first-run", "--disable-gpu",
         "--disable-background-timer-throttling",
         "--disable-backgrounding-occluded-windows",
         "--disable-renderer-backgrounding",
         "--user-data-dir=/tmp/cdp-profile", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # navigate the FIRST tab (it stays active/visible — a tab opened via
        # /json/new is backgrounded and its rAF gets frozen mid-animation)
        target = None
        err = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/list", timeout=3) as r:
                    pages = [t for t in json.load(r) if t.get("type") == "page"]
                if pages:
                    target = pages[0]
                    break
            except Exception as e:
                err = e
            time.sleep(0.5)
        if not target:
            raise RuntimeError(f"chrome debug port never came up: {err}")
        if not target:
            raise RuntimeError("chrome debug port never came up")
        s = ws_connect(target["webSocketDebuggerUrl"])
        cdp(s, 4, "Page.navigate", {"url": url})
        cdp_wait(s, 4)
        # keep the page foregrounded — headless throttles rAF for occluded pages
        t_end = time.time() + wait
        while time.time() < t_end:
            cdp(s, 6, "Page.bringToFront")
            cdp_wait(s, 6)
            time.sleep(min(1.0, max(0.05, t_end - time.time())))
        expr = os.environ.get("CDP_EVAL")
        if expr:
            cdp(s, 7, "Runtime.evaluate", {"expression": expr,
                                           "returnByValue": True})
            res = cdp_wait(s, 7).get("result", {})
            val = res.get("result", {}).get("value")
            evout = os.environ.get("CDP_EVAL_OUT")
            if evout and isinstance(val, str) and val.startswith("data:image/png;base64,"):
                with open(evout, "wb") as f:
                    f.write(base64.b64decode(val.split(",", 1)[1]))
                print("EVAL ->", evout, os.path.getsize(evout), "bytes")
            else:
                print("EVAL:", json.dumps(res)[:600])
        cdp(s, 1, "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": True})
        shot = cdp_wait(s, 1)
        data = shot.get("result", {}).get("data")
        if not data:
            raise RuntimeError("no screenshot: " + json.dumps(shot)[:300])
        with open(out, "wb") as f:
            f.write(base64.b64decode(data))
        print(out, os.path.getsize(out), "bytes")
    finally:
        chrome.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
