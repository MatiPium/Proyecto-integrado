(() => {
  const toggle = document.querySelector('.menu-toggle');
  const overlay = document.querySelector('.sidebar-overlay');
  const sidebar = document.querySelector('.sidebar');
  const mobile = window.matchMedia('(max-width: 850px)');
  const setMenu = (open, restoreFocus = true) => {
    document.body.classList.toggle('menu-open', open);
    toggle?.setAttribute('aria-expanded', String(open));
    if (overlay) overlay.hidden = !open;
    if (sidebar) sidebar.inert = mobile.matches && !open;
    if (open) sidebar?.querySelector('a')?.focus();
    else if (restoreFocus) toggle?.focus();
  };
  if (sidebar) sidebar.inert = mobile.matches;
  mobile.addEventListener('change', () => setMenu(false, false));
  toggle?.addEventListener('click', () => setMenu(!document.body.classList.contains('menu-open')));
  overlay?.addEventListener('click', () => setMenu(false));
  document.addEventListener('keydown', event => {
    if (!document.body.classList.contains('menu-open')) return;
    if (event.key === 'Escape') setMenu(false);
    if (event.key === 'Tab') {
      const links = [...sidebar.querySelectorAll('a, button, input, select')].filter(el => !el.disabled && el.offsetParent !== null);
      const first = links[0], last = links[links.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  });
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll('table.table').forEach(table => {
    if (table.closest('.table-responsive')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-responsive';
    table.before(wrapper);
    wrapper.append(table);
  });
  document.querySelectorAll('[data-upload-zone]').forEach(zone => {
    const input = zone.querySelector('input[type="file"]');
    const preview = zone.querySelector('[data-upload-preview]');
    const filename = zone.querySelector('[data-upload-name]');
    let objectUrl;
    if (!input) return;
    const update = () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      const file = input.files[0];
      filename.textContent = file ? file.name : 'Ningún archivo seleccionado';
      preview.hidden = true;
      preview.removeAttribute('src');
      if (file && file.type.startsWith('image/')) {
        objectUrl = URL.createObjectURL(file);
        preview.src = objectUrl;
        preview.hidden = false;
      }
    };
    input.addEventListener('change', update);
    preview.addEventListener('error', () => { preview.hidden = true; });
    ['dragenter', 'dragover'].forEach(name => zone.addEventListener(name, event => {
      event.preventDefault(); zone.classList.add('drag-over');
    }));
    ['dragleave', 'drop'].forEach(name => zone.addEventListener(name, event => {
      event.preventDefault(); zone.classList.remove('drag-over');
    }));
    zone.addEventListener('drop', event => {
      if (!event.dataTransfer.files.length) return;
      const transfer = new DataTransfer();
      transfer.items.add(event.dataTransfer.files[0]);
      input.files = transfer.files;
      update();
    });
  });
})();
