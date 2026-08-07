"""Serve the versioned read-only DreamCore Session Package API locally."""

from __future__ import annotations

import argparse
from pathlib import Path
from wsgiref.simple_server import make_server

import yaml

from dreamcore.api.http import ApiSettings, SessionApiApplication, build_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    transport = config["session_transport"]
    project_root = config_path.parent.parent
    package_root = project_root / transport["session_package_root"]
    settings = ApiSettings(
        max_signal_window_seconds=float(transport["max_signal_window_s"]),
        cors_allowed_origins=tuple(transport["cors_allowed_origins"]),
    )
    app = SessionApiApplication(build_registry(package_root), settings)
    host = str(transport["host"])
    port = int(transport["port"])
    print(f"DreamCore read-only API {transport['api_version']} on http://{host}:{port}")
    with make_server(host, port, app) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
