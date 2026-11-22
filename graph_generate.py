from functools import lru_cache
from io import BytesIO
from threading import Lock

from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from diagnostic_data import MAX_SPANS

STYLES = {
    "отличный": ("#009900", "Отличный пролёт"),
    "в норме": ("#AADD23", "Пролёт в норме"),
    "в горизонте": ("#FFD700", "Пролёт в горизонте"),
    "в контруклоне": ("#FF0033", "Пролёт в контруклоне"),
}
UNKNOWN = ("#808080", "Уклон не указан")
render_lock = Lock()


@lru_cache(maxsize=32)
def generate_diagnostic_plot(pipe_type, spans, defects, *, truncated=False):
    with render_lock:
        return render_plot(pipe_type, spans, defects, truncated)


def render_plot(pipe_type, spans, defects, truncated):
    figure = Figure(figsize=(4, min(12, max(4, len(spans) * 0.7))), dpi=100)
    ax = figure.subplots()
    figure.subplots_adjust(bottom=0.24, left=0.19, right=0.92)
    try:
        if not spans:
            ax.text(0.5, 0.5, "Нет данных о пролётах", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        else:
            draw_spans(ax, pipe_type, spans[:MAX_SPANS], defects)
            if truncated:
                ax.set_title("График показан частично", fontsize=9)
        with BytesIO() as output:
            figure.savefig(output, format="png")
            return output.getvalue()
    finally:
        figure.clear()


def draw_spans(ax, pipe_type, spans, defects):
    offset = 0.0
    legend = {}
    wells = []
    for span in spans:
        color, label = STYLES.get(span.slope, UNKNOWN)
        endpoint = offset + float(span.length)
        ax.plot([0, 0], [offset, endpoint], color=color, lw=4)
        if label not in legend:
            legend[label] = Line2D([0], [0], color=color, lw=4, label=label)
        if not wells or wells[-1] != (offset, span.first_well):
            wells.append((offset, span.first_well))
        wells.append((endpoint, span.last_well))
        offset = endpoint

    ax.scatter([0] * len(wells), [position for position, _ in wells], color="#3399FF", s=45, zorder=3)
    legend["Колодец"] = Line2D([], [], marker="o", color="#3399FF", linestyle="", label="Колодец")
    last_position = None
    for position, name in wells:
        left = position == last_position
        label = f"{pipe_type or ''} {name}".strip()
        if len(label) > 32:
            label = label[:31] + "…"
        ax.annotate(label, (0, position), xytext=(-7 if left else 7, 0),
                    textcoords="offset points", ha="right" if left else "left", va="center",
                    fontsize=8, parse_math=False)
        last_position = position
    marks = [float(distance) for distance in defects if distance <= offset]
    if marks:
        ax.scatter([0] * len(marks), marks, color="#FF9900", s=22, marker="s", zorder=4)
        legend["Дефект"] = Line2D([], [], marker="s", color="#FF9900", linestyle="", label="Дефект")
    pad = max(1, offset / 20)
    ax.set(ylim=(-pad, offset + pad), xlim=(-1, 1), ylabel="Расстояние (м)", xticks=[])
    ax.legend(handles=legend.values(), loc="upper center", bbox_to_anchor=(0.5, -0.03),
              fontsize=8, frameon=False)
