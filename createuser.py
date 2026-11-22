"""Create or restore an administrator through an explicit, interactive command."""

from getpass import getpass

import click
from psycopg2.errors import UniqueViolation

from security import hash_password


@click.command("create-admin")
@click.option("--username", prompt="Логин")
@click.option("--full-name", prompt="Полное имя")
@click.option("--reset-disabled", is_flag=True, help="Replace the password of a disabled administrator.")
def create_admin(username, full_name, reset_disabled):
    from flask import current_app

    username, full_name = username.strip(), full_name.strip()
    if not all(0 < len(field) <= 255 and "\0" not in field for field in (username, full_name)):
        raise click.ClickException("Логин и имя должны содержать от 1 до 255 символов.")
    password = getpass("Пароль: ")
    if password != getpass("Повторите пароль: "):
        raise click.ClickException("Пароли не совпадают.")
    try:
        hashed = hash_password(password)
        with current_app.extensions["db"].transaction() as cursor:
            if reset_disabled:
                cursor.execute("""
                    UPDATE users SET password=%s, full_name=%s, timestampdata=CURRENT_TIMESTAMP
                    WHERE username=%s AND role='Admin' AND password IS NULL
                """, (hashed, full_name, username))
                if not cursor.rowcount:
                    raise click.ClickException("Отключённая учётная запись администратора не найдена.")
            else:
                cursor.execute("""
                    INSERT INTO users (username, full_name, role, password, timestampdata)
                    VALUES (%s, %s, 'Admin', %s, CURRENT_TIMESTAMP)
                """, (username, full_name, hashed))
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    except UniqueViolation as error:
        raise click.ClickException("Учётная запись с этим логином уже существует.") from error
    click.echo("Учётная запись администратора готова.")
