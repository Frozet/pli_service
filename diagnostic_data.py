from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import NamedTuple

SLOPES = ("отличный", "в норме", "в горизонте", "в контруклоне")
FLOWS = ("против течения", "по течению")
MAX_SPANS = 100
MAX_DEFECTS = 200


class FormError(ValueError):
    pass


def required(form, key, label, limit=255):
    value = form.get(key, "").strip()
    if not value or len(value) > limit or "\0" in value:
        raise FormError(f"Заполните поле «{label}» (до {limit} символов).")
    return value


def positive_int(value, label, ceiling=2_147_483_647):
    if value is not None and len(value) <= 10 and value.isascii() and value.isdecimal():
        number = int(value)
        if 1 <= number <= ceiling:
            return number
    raise FormError(f"Укажите корректное значение поля «{label}».")


def parse_date(value, label="Дата"):
    try:
        day = date.fromisoformat(value)
        if day.isoformat() == value:
            return day
    except (TypeError, ValueError):
        pass
    raise FormError(f"Укажите корректную дату в поле «{label}».")


def metres(value, label, minimum=0):
    try:
        number = Decimal(value)
        if (len(value) <= 24 and number.is_finite() and minimum <= number <= 1_000_000
                and number.as_tuple().exponent >= -3):
            return number
    except (InvalidOperation, TypeError, ValueError):
        pass
    raise FormError(f"Укажите корректное расстояние в поле «{label}» (до трёх знаков после запятой).")


def coordinate_pair(value):
    try:
        latitude, longitude = map(float, value.split(","))
        if all(map(isfinite, (latitude, longitude))) and -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return latitude, longitude
    except (AttributeError, ValueError):
        pass
    raise FormError("Укажите координаты в формате «широта, долгота».")


class Span(NamedTuple):
    first_well: str
    flow: str
    slope: str
    length: Decimal
    last_well: str


class Defect(NamedTuple):
    description: str
    distance: Decimal


@dataclass(frozen=True)
class DiagnosticInput:
    short_title: str
    address: str
    diagnostic_type: str
    survey_date: date
    latitude: float
    longitude: float
    pipe_type: str
    diameter: int
    material: str
    distance: Decimal
    areaid: int
    spans: tuple[Span, ...]
    defects: tuple[Defect, ...]

    @classmethod
    def from_form(cls, form):
        spans = []
        groups = ("well", "flow", "slope", "span", "well2")
        for index in field_indices(form, groups, MAX_SPANS):
            first, flow, slope, length, last = (
                required(form, f"{group}_{index}", f"Пролёт {index + 1}") for group in groups
            )
            if flow not in FLOWS or slope not in SLOPES:
                raise FormError(f"Проверьте направление течения и уклон пролёта {index + 1}.")
            spans.append(Span(first, flow, slope, metres(length, "Пролёт", Decimal("0.001")), last))

        distance = metres(form.get("distance"), "Расстояние", Decimal("0.001"))
        if not spans or sum(span.length for span in spans) != distance:
            raise FormError("Сумма длин пролётов должна совпадать с расстоянием диагностики.")

        defects = []
        for index in field_indices(form, ("problem", "problemDistance"), MAX_DEFECTS):
            description = form.get(f"problem_{index}", "").strip()
            raw_distance = form.get(f"problemDistance_{index}", "").strip()
            if not description and not raw_distance:
                continue
            description = required(form, f"problem_{index}", f"Описание дефекта {index + 1}", 2000)
            defect_distance = metres(raw_distance, f"Расстояние до дефекта {index + 1}")
            if defect_distance > distance:
                raise FormError(f"Дефект {index + 1} находится за пределами диагностики.")
            defects.append(Defect(description, defect_distance))

        latitude, longitude = coordinate_pair(form.get("coordinates"))
        return cls(
            short_title=required(form, "name", "Название"),
            address=required(form, "address", "Адрес"),
            diagnostic_type=required(form, "diagnostic_type", "Тип диагностики"),
            survey_date=parse_date(form.get("date")),
            latitude=latitude,
            longitude=longitude,
            pipe_type=required(form, "type", "Тип трубопровода"),
            diameter=positive_int(form.get("diameter"), "Диаметр"),
            material=required(form, "material", "Материал"),
            distance=distance,
            areaid=positive_int(form.get("areaid"), "Участок"),
            spans=tuple(spans),
            defects=tuple(defects),
        )


def field_indices(form, prefixes, limit):
    indices = set()
    for key in form:
        prefix, separator, suffix = key.partition("_")
        if separator and prefix in prefixes:
            if (not suffix.isascii() or not suffix.isdecimal() or len(suffix) > 6
                    or str(int(suffix)) != suffix or len(form.getlist(key)) != 1):
                raise FormError("Проверьте порядок полей пролётов и дефектов.")
            indices.add(int(suffix))
    if len(indices) > limit:
        raise FormError(f"Максимальное количество блоков: {limit}.")
    return sorted(indices)


def legacy_spans(row):
    first_and_last = split_legacy(row["count_of_well"])
    lengths = split_legacy(row["distance_between_wells"])
    slopes = split_legacy(row["slope_between_wells"])
    flows = split_legacy(row["flow"])
    if len(first_and_last) != len(lengths) * 2 or not len(lengths) == len(slopes) == len(flows):
        raise FormError("Количество колодцев, пролётов, уклонов и направлений различается.")
    return tuple(
        Span(first_and_last[index * 2], flow, slope, metres(length, "Пролёт", Decimal("0.001")),
             first_and_last[index * 2 + 1])
        for index, (flow, slope, length) in enumerate(zip(flows, slopes, lengths, strict=True))
    )


def legacy_defects(row):
    raw = row["problems"] or ""
    distances = split_legacy(row["problems_distances"])
    # The original write path used commas, while some historical readers used semicolons.
    while distances and not distances[-1]:
        distances.pop()
        raw = raw.rstrip()
        if raw.endswith((",", ";")):
            raw = raw[:-1]
    if not distances and not raw.strip():
        return ()
    if len(distances) == 1:
        parts = [raw.strip()]
    else:
        candidates = {
            tuple(split_legacy(raw, delimiter))
            for delimiter in (",", ";")
            if len(raw.split(delimiter)) == len(distances)
        }
        if len(candidates) != 1:
            raise FormError("Невозможно однозначно сопоставить описания дефектов и расстояния.")
        parts = candidates.pop()
    if not all(parts):
        raise FormError("В старой записи присутствует дефект без описания.")
    return tuple(
        Defect(description, metres(distance, "Дефект"))
        for description, distance in zip(parts, distances, strict=True)
    )


def split_legacy(value, delimiter=","):
    return [part.strip() for part in value.split(delimiter)] if value else []
