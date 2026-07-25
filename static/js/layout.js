import { config } from './state.js';

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function readStoredWidth(key, fallback) {
    const value = Number.parseFloat(localStorage.getItem(key));
    return Number.isFinite(value)
        ? clamp(value, config.ui.panelWidths.min, config.ui.panelWidths.max)
        : fallback;
}

function applyPanelWidths(left, right) {
    const row = document.querySelector('.app-main-row');
    if (!row) return;
    row.style.setProperty('--panel-left-width', `${left}%`);
    row.style.setProperty('--panel-right-width', `${right}%`);
}

export function initializePanelResizers() {
    const row = document.querySelector('.app-main-row');
    const leftResizer = document.getElementById('leftPanelResizer');
    const rightResizer = document.getElementById('rightPanelResizer');
    if (!row || !leftResizer || !rightResizer) return;

    let left = readStoredWidth(config.storageKeys.leftPanelWidth, config.ui.panelWidths.left);
    let right = readStoredWidth(config.storageKeys.rightPanelWidth, config.ui.panelWidths.right);
    applyPanelWidths(left, right);

    const persistWidths = () => {
        localStorage.setItem(config.storageKeys.leftPanelWidth, left.toFixed(2));
        localStorage.setItem(config.storageKeys.rightPanelWidth, right.toFixed(2));
    };

    const startResize = (side) => (event) => {
        event.preventDefault();
        const bounds = row.getBoundingClientRect();
        const resizer = side === 'left' ? leftResizer : rightResizer;
        document.body.classList.add('is-resizing');
        resizer.classList.add('is-active');
        resizer.setPointerCapture(event.pointerId);

        const onMove = (moveEvent) => {
            const raw = side === 'left'
                ? ((moveEvent.clientX - bounds.left) / bounds.width) * 100
                : ((bounds.right - moveEvent.clientX) / bounds.width) * 100;
            const value = clamp(raw, config.ui.panelWidths.min, config.ui.panelWidths.max);
            if (side === 'left') left = value;
            else right = value;
            applyPanelWidths(left, right);
        };

        const onEnd = () => {
            document.body.classList.remove('is-resizing');
            resizer.classList.remove('is-active');
            persistWidths();
            resizer.removeEventListener('pointermove', onMove);
            resizer.removeEventListener('pointerup', onEnd);
            resizer.removeEventListener('pointercancel', onEnd);
        };

        resizer.addEventListener('pointermove', onMove);
        resizer.addEventListener('pointerup', onEnd);
        resizer.addEventListener('pointercancel', onEnd);
    };

    leftResizer.addEventListener('pointerdown', startResize('left'));
    rightResizer.addEventListener('pointerdown', startResize('right'));

    const bindKeyboardResize = (resizer, side) => {
        resizer.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            event.preventDefault();
            const step = event.shiftKey ? 3 : 1;
            const direction = event.key === 'ArrowRight' ? 1 : -1;
            if (side === 'left') {
                left = clamp(left + (direction * step), config.ui.panelWidths.min, config.ui.panelWidths.max);
            } else {
                right = clamp(right - (direction * step), config.ui.panelWidths.min, config.ui.panelWidths.max);
            }
            applyPanelWidths(left, right);
            persistWidths();
        });
    };

    bindKeyboardResize(leftResizer, 'left');
    bindKeyboardResize(rightResizer, 'right');
}
