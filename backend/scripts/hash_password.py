"""Generate an argon2 hash for APP_PASSWORD_HASH.

Usage: uv run python scripts/hash_password.py
"""

import getpass

from argon2 import PasswordHasher


def main() -> None:
    password = getpass.getpass("Password to hash: ")
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    print(PasswordHasher().hash(password))


if __name__ == "__main__":
    main()
