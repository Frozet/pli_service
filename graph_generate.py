import matplotlib
matplotlib.use('Agg')  # Используем 'Agg' бэкэнд для работы без GUI
import matplotlib.pyplot as plt
import io

def generate_diagnostic_plot(diagnostic):
    distances = list(map(float, diagnostic['distance_between_wells'].split(',')))
    slopes = list(map(float, diagnostic['slope_between_wells'].split(',')))
    wells = diagnostic['count_of_well'].split(',')
    problems_distances = list(map(float, diagnostic['problems_distances'].split(',')))
    total_distance = float(diagnostic['distance'])
    flow = diagnostic['flow'].split(',')

    fig, ax = plt.subplots(figsize=(4, 6))

    current_distance = 0

    # Отрисовка линии пролета
    for i, distance in enumerate(distances):
        color = 'green' if (slopes[i] < 0 and flow[i] == 'по течению') or (slopes[i] > 0 and flow[i] == 'против течения') else 'red'
        ax.plot([0, 0], [current_distance, current_distance + distance], color=color, lw=4)
        current_distance += distance

    # Отрисовка колодцев поверх линии
    current_distance = 0
    for i, distance in enumerate(distances):
        ax.scatter([0], [current_distance], color='blue', s=120, zorder=3)
        ax.text(0.1, current_distance, f'КК {wells[i]}', va='center', fontsize=10, zorder=4)
        current_distance += distance

    ax.scatter([0], [current_distance], color='blue', s=120, zorder=3)
    ax.text(0.1, current_distance, f'КК {wells[-1]}', va='center', fontsize=10, zorder=4)

    # Отрисовка проблем поверх линии
    for i, problem_distance in enumerate(problems_distances):
        ax.scatter([0], [problem_distance], color='orange', s=120, marker='s', zorder=3)

    # Настройка шкалы расстояний
    ax.set_xlim([-1, 1])
    ax.set_ylim([-0.5, total_distance + 0.5])
    ax.set_ylabel('Расстояние (м)')

    ax.axis('on')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)

    return buf