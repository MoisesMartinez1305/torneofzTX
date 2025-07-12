// static/js/modo_invitado.js

document.addEventListener('DOMContentLoaded', function() {
    // Expand all matchdays
    document.getElementById('expandAll')?.addEventListener('click', () => {
        document.querySelectorAll('.accordion-collapse').forEach(collapse => {
            if (!collapse.classList.contains('show')) {
                new bootstrap.Collapse(collapse, { show: true });
            }
        });
    });

    // Collapse all matchdays
    document.getElementById('collapseAll')?.addEventListener('click', () => {
        document.querySelectorAll('.accordion-collapse.show').forEach(collapse => {
            new bootstrap.Collapse(collapse, { hide: true });
        });
    });

    // Función para actualizar los textos de las pestañas
    function updateTabTexts(activeTabId) {
        // Primero resetear todos los textos a "Mostrar"
        document.querySelectorAll('.toggle-tab .tab-text').forEach(textElement => {
            const tabId = textElement.closest('.toggle-tab').getAttribute('data-bs-target').replace('#', '');
            if (tabId.includes('jornadas')) {
                textElement.textContent = 'Mostrar Jornadas';
            } else if (tabId.includes('tabla')) {
                textElement.textContent = 'Mostrar Clasificación';
            } else if (tabId.includes('goleadores')) {
                textElement.textContent = 'Mostrar Goleadores';
            } else if (tabId.includes('eliminatorias')) {
                textElement.textContent = 'Mostrar Eliminatorias';
            }
        });

        // Luego establecer texto en mayúsculas solo para la pestaña activa
        if (activeTabId) {
            const activeButton = document.querySelector(`[data-bs-target="#${activeTabId}"] .tab-text`);
            if (activeButton) {
                if (activeTabId.includes('jornadas')) {
                    activeButton.textContent = 'JORNADAS';
                } else if (activeTabId.includes('tabla')) {
                    activeButton.textContent = 'CLASIFICACIÓN';
                } else if (activeTabId.includes('goleadores')) {
                    activeButton.textContent = 'GOLEADORES TOP 20';
                } else if (activeTabId.includes('eliminatorias')) {
                    activeButton.textContent = 'ELIMINATORIAS';
                }
            }
        }
    }

    // Configurar eventos para los botones de pestaña
    document.querySelectorAll('.toggle-tab').forEach(button => {
        button.addEventListener('click', function() {
            const targetId = this.getAttribute('data-bs-target').replace('#', '');
            updateTabTexts(targetId);
            
            // Guardar la pestaña activa en localStorage
            localStorage.setItem('activeTab', targetId);
        });
    });

    // Manejar el evento de cambio de pestaña de Bootstrap
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(event) {
            const targetId = event.target.getAttribute('data-bs-target').replace('#', '');
            updateTabTexts(targetId);
            
            // Guardar la pestaña activa en localStorage
            localStorage.setItem('activeTab', targetId);
        });
    });

    // Intentar recuperar la pestaña activa del localStorage
    const savedTab = localStorage.getItem('activeTab');
    if (savedTab && document.querySelector(`[data-bs-target="#${savedTab}"]`)) {
        const tab = new bootstrap.Tab(document.querySelector(`[data-bs-target="#${savedTab}"]`));
        tab.show();
        updateTabTexts(savedTab);
    } else {
        // Inicializar con la primera pestaña activa por defecto
        const activeTab = document.querySelector('.nav-link.active');
        if (activeTab) {
            const activeTabId = activeTab.getAttribute('data-bs-target').replace('#', '');
            updateTabTexts(activeTabId);
        }
    }

    // Mostrar automáticamente la primera liga
    if (document.querySelector('.collapse')) {
        const firstCollapse = document.querySelector('.collapse');
        new bootstrap.Collapse(firstCollapse, {toggle: true});
    }
    
    // Mejorar interacción de las cards
    document.querySelectorAll('.liga-card').forEach(card => {
        card.addEventListener('click', function() {
            const targetId = this.getAttribute('onclick').match(/'(.*?)'/)[1];
            const targetElement = document.getElementById(targetId);
            
            // Desplazamiento suave al elemento
            targetElement.scrollIntoView({behavior: 'smooth', block: 'start'});
            
            // Resaltar la sección abierta
            document.querySelectorAll('.collapse').forEach(collapse => {
                if (collapse.id !== targetId) {
                    bootstrap.Collapse.getInstance(collapse)?.hide();
                }
            });
        });
    });
});