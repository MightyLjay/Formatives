"""The dependency-free .env loader: reads keys, respects existing env, ignores junk."""
import os

from market.config import load_dotenv


def test_loads_keys_and_respects_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        'ODDS_API_KEY="abc123"\n'
        "EMPTY_LINE_BELOW=\n"
        "\n"
        "QUOTED='single'\n"
        "ALREADY_SET=fromfile\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    monkeypatch.setenv("ALREADY_SET", "fromenv")  # explicit env must win over the file

    load_dotenv(str(env))

    assert os.environ["ODDS_API_KEY"] == "abc123"     # quotes stripped
    assert os.environ["QUOTED"] == "single"
    assert os.environ["ALREADY_SET"] == "fromenv"     # precedence preserved


def test_missing_file_is_noop(tmp_path):
    load_dotenv(str(tmp_path / "does-not-exist.env"))  # must not raise


def test_loads_utf8_bom_file(tmp_path, monkeypatch):
    # PowerShell's `Out-File -Encoding utf8` writes a UTF-8 BOM; the loader must strip it so the
    # first key name isn't corrupted to "﻿ODDS_API_KEY".
    env = tmp_path / ".env"
    env.write_bytes(b"\xef\xbb\xbfODDS_API_KEY=frombom\n")
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    load_dotenv(str(env))
    assert os.environ.get("ODDS_API_KEY") == "frombom"
