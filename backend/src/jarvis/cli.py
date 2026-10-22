from __future__ import annotations

import argparse
import getpass

from jarvis.auth.passwords import PasswordManager
from jarvis.auth.service import AuthService
from jarvis.core.config import Settings
from jarvis.infrastructure.auth_repository import (
    OwnerAlreadyExistsError,
    PostgreSQLAuthRepository,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m jarvis.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create_owner = commands.add_parser(
        "create-owner",
        help="Create the first owner, household and linked person",
    )
    create_owner.add_argument("--email", required=True)
    create_owner.add_argument("--household", required=True)
    create_owner.add_argument("--display-name", required=True)
    return parser


def _read_password() -> str:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    return password


def create_owner(email: str, household: str, display_name: str) -> None:
    normalized_email = AuthService.normalize_email(email)
    if "@" not in normalized_email:
        raise SystemExit("Email address is invalid")
    password_hash = PasswordManager().hash(_read_password())
    repository = PostgreSQLAuthRepository(Settings.from_environment())
    try:
        user_id = repository.create_first_owner(
            email=normalized_email,
            password_hash=password_hash,
            household_name=household.strip(),
            display_name=display_name.strip(),
        )
    except OwnerAlreadyExistsError as error:
        raise SystemExit("The first owner has already been created") from error
    print(f"First owner created: {user_id}")


def main() -> None:
    arguments = _parser().parse_args()
    if arguments.command == "create-owner":
        create_owner(arguments.email, arguments.household, arguments.display_name)


if __name__ == "__main__":
    main()
