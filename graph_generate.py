import matplotlib
matplotlib.use('Agg')  # Используем 'Agg' бэкэнд для работы без GUI
import matplotlib.pyplot as plt
import io

def generate_diagnostic_plot(diagnostic):
    distances = list(map(float, diagnostic['distance_between_wells'].split(',')))
    slopes = list(map(str, diagnostic['slope_between_wells'].split(',')))
    wells = diagnostic['count_of_well'].split(',')
    if diagnostic['problems_distances']:
        problems_distances = list(map(float, diagnostic['problems_distances'].split(',')))
    total_distance = float(diagnostic['distance'])
    if len(slopes) < 3:
        plot_len = 4
    else:
        plot_len = len(slopes) * 2
    fig, ax = plt.subplots(figsize=(3, plot_len))

    # Словарь для легенды
    legend_elements = []
    current_distance = 0

    # Отрисовка линии пролета
    for i, distance in enumerate(distances):
        match slopes[i]:
            case 'отличный':
                color = '#009900'
                description = 'Отличный пролет'
            case 'в норме':
                color = '#AADD23'
                description = 'Пролет в норме'
            case 'в горизонте':
                color = '#FFD700'
                description = 'Пролет в горизонте'
            case 'в контруклоне':
                color = '#FF0033'
                description = 'Пролет в контруклоне'
        ax.plot([0, 0], [current_distance, current_distance + distance], color=color, lw=4)
        current_distance += distance

        # Добавляем описание в легенду (один раз для каждого типа)
        if description not in [element.get_label() for element in legend_elements]:
            legend_elements.append(plt.Line2D([0], [0], color=color, lw=4, label=description))

   # Отрисовка колодцев поверх линии
    current_distance, i = 0, 0
    for well_f in wells[:-1:2]:
        well_l = wells[i+1]
        ax.scatter([0], [current_distance], color='#3399FF', s=120, zorder=3)
        ax.text(0.1, current_distance, f'{diagnostic["type"]} {well_f}', va='center', fontsize=10, zorder=4)
        # Обновляем текущее расстояние
        current_distance += distances[i//2]
        if i + 1 != len(wells) - 1: # Рисуем колодец, если он не последний
            if well_l != wells[i+2]: # Рисуем колодец, только если он не дублируется
                ax.scatter([0], [current_distance], color='#3399FF', s=120, zorder=3)
                ax.text(-0.3, current_distance, f'{diagnostic["type"]} {well_l}', va='center', fontsize=10, zorder=4)
        i += 2

    # Рисуем последний колодец
    ax.scatter([0], [current_distance], color='#3399FF', s=120, zorder=3)
    ax.text(0.1, current_distance, f'{diagnostic["type"]} {wells[-1]}', va='center', fontsize=10, zorder=4)

    # Отрисовка проблем поверх линии
    if diagnostic['problems_distances']:
        for i, problem_distance in enumerate(problems_distances):
            ax.scatter([0], [problem_distance], color='#FF9900', s=30, marker='s', zorder=3)

            # Добавляем проблему в легенду (один раз)
            if 'Проблема' not in [element.get_label() for element in legend_elements]:
                legend_elements.append(plt.Line2D([0], [0], marker='s', color='#FF9900', markersize=6, label='Проблема'))

     # Добавляем колодец в легенду (один раз)
    if 'Колодец' not in [element.get_label() for element in legend_elements]:
        legend_elements.append(plt.Line2D([0], [0], marker='o', color='#3399FF', markersize=10, label='Колодец'))


    # Настройка шкалы расстояний
    ax.set_xlim([-1, 1])
    # Если дистанция меньше 20 метров, делаем отсупы по оси y по 1м, иначе по 5% от дистанции
    if total_distance < 20:
        start_point = -1
        end_point = 1
    else:
        start_point = -(total_distance // 20)
        end_point = total_distance // 20
    ax.set_ylim([start_point, total_distance + end_point])
    ax.set_ylabel('Расстояние (м)')
    ax.axis('on')

    if plot_len == 4:
        leg_pos = -0.3
    else:
        leg_pos = -0.15

    # Добавляем легенду под графиком
    ax.legend(handles=legend_elements, loc='lower center', bbox_to_anchor=(0.5, leg_pos), fontsize=8, frameon=False)

    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)

    return buf
