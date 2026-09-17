const DEFAULT_ROW_HEIGHT = 76;
const OVERSCAN = 6;

export function createVirtualList(container, createItem, rowHeight = DEFAULT_ROW_HEIGHT) {
    const scrollHost = container.closest('.section-body') || container;
    const root = document.createElement('div');
    const spacer = document.createElement('div');
    const viewport = document.createElement('div');
    let items = [];
    let frameId = null;

    root.className = 'virtual-list-root';
    spacer.className = 'virtual-list-spacer';
    viewport.className = 'virtual-list-viewport';
    root.append(spacer, viewport);
    container.replaceChildren(root);

    const render = () => {
        frameId = null;
        const visibleHeight = scrollHost.clientHeight || 400;
        const start = Math.max(0, Math.floor(scrollHost.scrollTop / rowHeight) - OVERSCAN);
        const end = Math.min(items.length, Math.ceil((scrollHost.scrollTop + visibleHeight) / rowHeight) + OVERSCAN);
        spacer.style.height = `${items.length * rowHeight}px`;
        viewport.style.transform = `translateY(${start * rowHeight}px)`;
        viewport.replaceChildren(...items.slice(start, end).map(createItem));
    };

    const schedule = () => {
        if (frameId !== null) return;
        frameId = requestAnimationFrame(render);
    };

    scrollHost.addEventListener('scroll', schedule, { passive: true });
    // Panel resizes (layout.js drag) change clientHeight without a scroll
    // event; without an observer the visible slice would stay stale until
    // the next scroll.
    let observer = null;
    if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(schedule);
        observer.observe(scrollHost);
    }

    return {
        setItems(nextItems) {
            items = nextItems;
            schedule();
        },
        destroy() {
            if (frameId !== null) cancelAnimationFrame(frameId);
            scrollHost.removeEventListener('scroll', schedule);
            if (observer) observer.disconnect();
        },
    };
}
