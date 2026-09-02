"""SQL 文件库: 从本地目录或远程 Linux(SFTP) 读取 SQL 文件。"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def backend():
    host = _env("SQL_FILE_HOST")
    if host:
        return _SftpBackend(host)
    return _LocalBackend()


def base_dir() -> Path:
    return Path(_env("SQL_FILE_DIR", str(PROJECT_ROOT / "sql_files")))


class _LocalBackend:
    label = "本地目录"

    def __init__(self):
        self.root = base_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise ValueError("路径越界")
        return target

    def list_files(self, relative: str = "") -> list[dict]:
        root = self._resolve(relative)
        if not root.exists():
            return []
        entries = []
        for child in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            rel = str(child.relative_to(self.root))
            entries.append(
                {
                    "path": rel,
                    "name": child.name,
                    "type": "file" if child.is_file() else "dir",
                    "size": child.stat().st_size if child.is_file() else 0,
                    "sql": child.suffix.lower() in (".sql", ".hql", ".ddl", ".ddl.sql"),
                }
            )
        return entries

    def read_file(self, relative: str) -> str:
        return self._resolve(relative).read_text(encoding="utf-8", errors="replace")


class _SftpBackend:
    label = "远程 Linux(SFTP)"

    def __init__(self, host: str):
        import paramiko

        self.host = host
        self.user = _env("SQL_FILE_USER", "root")
        self.password = _env("SQL_FILE_PASSWORD", "") or None
        key_path = _env("SQL_FILE_KEY", "")
        self.key = paramiko.RSAKey.from_private_key_file(key_path) if key_path else None
        self.remote_dir = _env("SQL_FILE_DIR", "/root/sql_files").rstrip("/")

    def _connect(self):
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self.host, username=self.user, password=self.password,
                       pkey=self.key, timeout=10)
        return client

    def list_files(self, relative: str = "") -> list[dict]:
        client = self._connect()
        try:
            sftp = client.open_sftp()
            remote = f"{self.remote_dir}/{relative}".rstrip("/")
            entries = []
            for item in sorted(sftp.listdir_attr(remote), key=lambda a: (a.st_mode & 0o4000 == 0, a.filename.lower())):
                is_dir = bool(item.st_mode & 0o4000)
                entries.append(
                    {
                        "path": f"{relative}/{item.filename}".strip("/"),
                        "name": item.filename,
                        "type": "dir" if is_dir else "file",
                        "size": item.st_size if not is_dir else 0,
                        "sql": not is_dir and item.filename.lower().endswith((".sql", ".hql", ".ddl")),
                    }
                )
            sftp.close()
            return entries
        finally:
            client.close()

    def read_file(self, relative: str) -> str:
        client = self._connect()
        try:
            sftp = client.open_sftp()
            with sftp.open(f"{self.remote_dir}/{relative}", "r") as fp:
                content = fp.read().decode("utf-8", errors="replace")
            sftp.close()
            return content
        finally:
            client.close()
