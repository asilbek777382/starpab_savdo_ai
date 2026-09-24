import sys
from io import StringIO

from sqlalchemy import select

from app import cli
from app.models import Account
from app.services.auth import verify_password


async def test_make_admin_creates_account(session):
    msg = await cli.make_admin("90 555 66 77", "Asilbek", "kuchli-parol-1")
    assert "+998905556677" in msg
    account = await session.scalar(select(Account))
    assert account.is_platform_admin and verify_password(account.password_hash, "kuchli-parol-1")


def test_password_stdin_flag_reads_password(monkeypatch):
    seen = {}

    async def fake_make_admin(phone, name, password):
        seen.update(phone=phone, password=password)
        return "ok"

    monkeypatch.setattr(cli, "make_admin", fake_make_admin)
    monkeypatch.setattr(sys, "argv", ["app.cli", "make-admin", "+998905556677", "--password-stdin"])
    monkeypatch.setattr(sys, "stdin", StringIO("maxfiy-parol-9\n"))
    assert cli.main() == 0
    assert seen == {"phone": "+998905556677", "password": "maxfiy-parol-9"}
