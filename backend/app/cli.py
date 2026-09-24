"""Boshqaruv buyruqlari.

    uv run python -m app.cli make-admin +998901234567 [--name "Ism"]
Akkaunt bo'lmasa yaratiladi (parol so'raladi), bo'lsa platforma admini qilinadi.
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import Account
from app.services.auth import AuthError, hash_password, parse_phone, validate_password


async def make_admin(phone_raw: str, name: str, password: str | None) -> str:
    phone = parse_phone(phone_raw)
    async with get_sessionmaker()() as session:
        account = await session.scalar(select(Account).where(Account.phone == phone))
        if account is None:
            if password is None:
                password = getpass.getpass("Yangi parol: ")
            validate_password(password)
            account = Account(phone=phone, name=name or "Admin", password_hash=hash_password(password))
            session.add(account)
        account.is_platform_admin = True
        await session.commit()
        return f"{phone} — platforma admini"


def main() -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make-admin")
    p.add_argument("phone")
    p.add_argument("--name", default="")
    p.add_argument("--password", default=None, help="Berilmasa so'raladi")
    p.add_argument("--password-stdin", action="store_true", help="Parolni stdin'dan o'qish (skriptlar uchun)")
    args = parser.parse_args()
    if args.password_stdin:
        args.password = sys.stdin.readline().rstrip("\n")
    try:
        print(asyncio.run(make_admin(args.phone, args.name, args.password)))
    except AuthError as exc:
        print(f"Xato: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
