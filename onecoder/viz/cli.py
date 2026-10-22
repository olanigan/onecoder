"""`onecoder viz`: serve the project's work graph, or print it as JSON."""

import json

from ..track import cli as track_cli
from .server import make_server
from .snapshot import snapshot


def cmd_viz(a):
    root = track_cli._get_root()
    if a.print_json:
        print(json.dumps(snapshot(root), indent=2))
        return 0
    server = make_server(root, host=a.host, port=a.port)
    url = f"http://{a.host}:{server.server_address[1]}/"
    print(f"onecoder viz: {root.name} at {url}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
