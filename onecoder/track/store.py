"""Track store resolver: Factory for LocalTrackStore and RemoteTrackClient."""

import os
from pathlib import Path
from typing import Optional, Union

from .local import LocalTrackStore
from .remote import RemoteTrackClient
from .. import policy as pol


def get_track_store(root: Optional[Path] = None, backend: Optional[str] = None,
                    policy: Optional[dict] = None) -> Union[LocalTrackStore, RemoteTrackClient]:
    root = root or Path.cwd()
    if policy is None:
        try:
            policy = pol.load(root)
        except Exception:
            policy = {}

    track_cfg = policy.get("track", {}) if isinstance(policy, dict) else {}
    target_backend = backend or os.environ.get("ONECODER_TRACK_BACKEND") or track_cfg.get("backend", "auto")

    secret = os.environ.get("TRACK_PUSH_SECRET") or os.environ.get("ONECODER_TRACK_SECRET")
    endpoint = track_cfg.get("endpoint") or os.environ.get("TRACK_API_ENDPOINT") or "https://apps.lanig.workers.dev"

    if target_backend == "remote":
        return RemoteTrackClient(endpoint=endpoint, secret=secret, root=root)
    elif target_backend == "local":
        return LocalTrackStore(root=root, policy=policy)
    else:  # auto
        if secret:
            return RemoteTrackClient(endpoint=endpoint, secret=secret, root=root)
        return LocalTrackStore(root=root, policy=policy)
