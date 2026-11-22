from datetime import date
from decimal import Decimal

import click
from flask import current_app

from areas_requests import get_area
from db_requests import save_diagnostic
from diagnostic_data import Defect, DiagnosticInput, Span


@click.command("seed-diagnostics")
@click.option("--area-id", type=click.IntRange(min=1), required=True)
@click.option("--count", type=click.IntRange(1, 2000), default=10, show_default=True)
def seed_diagnostics(area_id, count):
    """Add sample diagnostics to a selected area in a development database."""
    with current_app.extensions["db"].transaction() as cursor:
        if not get_area(cursor, area_id):
            raise click.ClickException("Участок не найден.")
        for index in range(1, count + 1):
            distance = Decimal(20 + index % 25)
            sample = DiagnosticInput(
                short_title=f"Тестовая диагностика {index}",
                address="Иркутск",
                diagnostic_type="Повреждение",
                survey_date=date.today(),
                latitude=52.27,
                longitude=104.31,
                pipe_type="КК",
                diameter=200,
                material="Пластик",
                distance=distance,
                areaid=area_id,
                spans=(Span("А", "по течению", "в норме", distance, "Б"),),
                defects=(Defect("Тестовый дефект", distance / 2),),
            )
            save_diagnostic(cursor, sample, "Демонстрационные данные")
    click.echo(f"Добавлено диагностик: {count}.")
