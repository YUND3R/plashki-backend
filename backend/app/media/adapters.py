from pathlib import Path


class LocalFileStorage:
    def __init__(self, root: str | Path, public_base_url: str = "") -> None:
        root_path = Path(root)
        self._root = root_path if root_path.is_absolute() else Path.cwd() / root_path
        self._public_base_url = public_base_url.strip().rstrip("/")

    def save(self, filename: str, body: bytes) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / filename).write_bytes(body)

    def delete(self, filename: str) -> None:
        try:
            (self._root / filename).unlink(missing_ok=True)
        except OSError:
            pass

    def public_url(self, filename: str, request_base_url: str = "") -> str:
        path = f"/files/{filename}"
        base = self._public_base_url or request_base_url.strip().rstrip("/")
        return f"{base}{path}"
