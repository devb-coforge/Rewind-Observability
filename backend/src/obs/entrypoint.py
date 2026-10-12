from __future__ import annotations

import os
from pathlib import Path

from obs.main import create_app


def main() -> None:
    data = Path(os.environ.get("OBS_DATA_DIR", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        uid = int(os.environ.get("PUID", "1000"))
        gid = int(os.environ.get("PGID", "1000"))
        for root, dirs, files in os.walk(data):
            os.chown(root, uid, gid)
            for name in [*dirs, *files]:
                os.chown(os.path.join(root, name), uid, gid)
        os.setgid(gid)
        os.setuid(uid)
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
