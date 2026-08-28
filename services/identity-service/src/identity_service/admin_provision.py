import argparse
import asyncio
import getpass
from collections.abc import Sequence

from identity_service.application import AdminAlreadyExists, provision_administrator
from identity_service.db import dispose_engine, get_session_factory
from identity_service.schemas import LoginRequest


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the first local administrator without exposing a public API."
    )
    parser.add_argument("--email", required=True)
    return parser.parse_args(arguments)


async def provision(email: str) -> None:
    password = getpass.getpass("Administrator password: ")
    repeated_password = getpass.getpass("Repeat administrator password: ")
    if password != repeated_password:
        raise ValueError("password confirmation does not match")
    if len(password) < 12:
        raise ValueError("administrator password must be at least 12 characters")
    credentials = LoginRequest(email=email, password=password)
    try:
        async with get_session_factory()() as db:
            await provision_administrator(
                db=db,
                email=credentials.email,
                password=credentials.password,
            )
            await db.commit()
    except AdminAlreadyExists as exc:
        raise ValueError("an identity account already uses this email") from exc


async def provision_and_dispose(email: str) -> None:
    try:
        await provision(email)
    finally:
        await dispose_engine()


def main(arguments: Sequence[str] | None = None) -> None:
    parsed = parse_arguments(arguments)
    asyncio.run(provision_and_dispose(parsed.email))


if __name__ == "__main__":
    main()
