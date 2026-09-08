export function bindStaticEvents(app) {
    document.addEventListener('click', (event) => {
        const target = event.target.closest('[data-action]');
        if (!target) return;

        const action = target.dataset.action;
        const section = target.dataset.section;
        const contextAction = target.dataset.contextAction;
        const separator = target.dataset.separator;

        if (action === 'createFile') event.stopPropagation();
        if (action === 'toggleSection') return app.toggleSection(section);
        if (action === 'ctxAction') return app.ctxAction(contextAction);
        if (action === 'setPathSeparator') {
            const input = document.getElementById('pathSep');
            if (input) input.value = separator || '';
            return;
        }
        if (action === 'removeKeyValueRow') {
            target.closest('.d-flex')?.remove();
            return;
        }
        if (action === 'closeOperationSummary') return app.closeOperationSummary();
        // Form controls act on 'change' (listener below): the click phase
        // re-enters with no argument — for toggleSelectAll it would clobber
        // the pending selection rebuild, and for SELECTs it rebuilds the
        // options while the dropdown is open.
        if (action === 'toggleSelectAll') return;
        if (target.tagName === 'SELECT') return;

        const handler = app[action];
        if (typeof handler === 'function') handler.call(app);
    });

    document.addEventListener('change', (event) => {
        const target = event.target;
        const action = target.dataset.action;
        if (!action) return;

        if (action === 'toggleSelectAll') {
            app.toggleSelectAll(target.checked);
            return;
        }
        const handler = app[action];
        if (typeof handler === 'function') handler.call(app);
    });

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const target = event.target.closest('[data-action][role="button"], [data-action][role="menuitem"]');
        if (!target) return;
        event.preventDefault();
        target.click();
    });
}
