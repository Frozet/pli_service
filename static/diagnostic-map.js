const mapContainer = document.querySelector('#diagnostic-map');
if (mapContainer && window.ymaps) {
    window.ymaps.ready(() => {
        const data = JSON.parse(document.querySelector('#map-diagnostics').textContent);
        const icons = document.querySelector('#map-icons').dataset;
        const types = {
            'Найден колодец': icons.mark3,
            'Приемка': icons.mark4,
            'Без повреждений': icons.mark1,
            'Повреждение': icons.mark2,
        };
        const map = new window.ymaps.Map(mapContainer, {center: [52.27, 104.31], zoom: 12});
        data.forEach(diagnostic => {
            const link = document.createElement('a');
            link.href = diagnostic.url;
            link.textContent = diagnostic.short_title || 'Диагностика';
            const icon = Object.hasOwn(types, diagnostic.diagnostic_type) ? types[diagnostic.diagnostic_type] : icons.mark1;
            const marker = new window.ymaps.Placemark(
                [diagnostic.latitude, diagnostic.longitude],
                {balloonContent: link.outerHTML},
                {
                    iconLayout: 'default#image',
                    iconImageHref: icon,
                    iconImageSize: [35, 35],
                    iconImageOffset: [-17, -34],
                },
            );
            map.geoObjects.add(marker);
        });
    });
} else if (mapContainer) {
    mapContainer.hidden = true;
    document.querySelector('#map-fallback').hidden = false;
}
