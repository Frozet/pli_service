document.querySelectorAll('[data-repeater]').forEach(section => {
    const blocks = section.querySelector('[data-blocks]');
    const add = section.querySelector('[data-add]');
    const template = section.querySelector('template');
    const limit = Number(section.dataset.limit);
    const minimum = Number(section.dataset.minimum);
    let nextIndex = blocks.children.length;

    function updateControls() {
        const count = blocks.children.length;
        add.disabled = count >= limit;
        Array.from(blocks.children).forEach((block, index) => {
            block.querySelector('[data-block-number]').textContent = index + 1;
            block.querySelector('[data-remove]').disabled = count <= minimum;
        });
    }

    add.addEventListener('click', () => {
        const added = template.content.cloneNode(true);
        added.querySelectorAll('[id], [name], [for]').forEach(element => {
            ['id', 'name', 'for'].forEach(attribute => {
                if (element.hasAttribute(attribute)) {
                    element.setAttribute(attribute, element.getAttribute(attribute).replace('__INDEX__', nextIndex));
                }
            });
        });
        nextIndex += 1;
        blocks.append(added);
        updateControls();
        blocks.lastElementChild.querySelector('input, textarea').focus();
    });

    blocks.addEventListener('click', event => {
        if (event.target.matches('[data-remove]') && blocks.children.length > minimum) {
            event.target.closest('[data-block]').remove();
            updateControls();
            add.focus();
        }
    });

    updateControls();
});

const mapElement = document.querySelector('#map');
if (mapElement && window.ymaps) {
    window.ymaps.ready(() => {
        const field = document.querySelector('#coordinates');
        function fieldCoordinates() {
            const parts = field.value.trim().split(',');
            if (parts.length !== 2 || parts.some(part => !part.trim())) return null;
            const [latitude, longitude] = parts.map(Number);
            return Number.isFinite(latitude) && Math.abs(latitude) <= 90 &&
                Number.isFinite(longitude) && Math.abs(longitude) <= 180 ? [latitude, longitude] : null;
        }
        const center = fieldCoordinates() || [52.27, 104.31];
        const map = new window.ymaps.Map(mapElement, {center, zoom: 13});
        const marker = new window.ymaps.Placemark(center, {}, {
            iconLayout: 'default#image',
            iconImageHref: mapElement.dataset.marker,
            iconImageSize: [35, 35],
            iconImageOffset: [-17, -34],
            draggable: true,
        });
        map.geoObjects.add(marker);
        function select(coordinates) {
            marker.geometry.setCoordinates(coordinates);
            field.value = coordinates.join(',');
        }
        map.events.add('click', event => select(event.get('coords')));
        marker.events.add('dragend', () => select(marker.geometry.getCoordinates()));
        field.addEventListener('change', () => {
            const coordinates = fieldCoordinates();
            if (coordinates) {
                marker.geometry.setCoordinates(coordinates);
                map.setCenter(coordinates);
            }
        });
    });
}
