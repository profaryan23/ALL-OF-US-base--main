document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-color-editor]').forEach(editor => {
    const rows = editor.querySelector('[data-color-rows]');
    const reindex = () => rows.querySelectorAll('.color-editor-row').forEach((row, i) => {
      row.querySelector('input[type=file]').name = `color_photo_${i}`;
    });
    editor.querySelector('[data-add-color]').addEventListener('click', () => {
      if (rows.children.length >= 20) return;
      const row = document.createElement('div');
      row.className = 'color-editor-row';
      row.innerHTML = '<label>Color name<input name="color_name" maxlength="60" required></label><label>Color photo<input type="file" accept="image/jpeg,image/png,image/webp"></label><button type="button" data-remove-color>Remove</button>';
      rows.append(row);
      reindex();
    });
    editor.addEventListener('click', event => {
      if (event.target.matches('[data-remove-color]')) {
        event.target.closest('.color-editor-row').remove();
        reindex();
      }
    });
  });
  document.querySelectorAll('[data-color-photo]').forEach(input => {
    input.addEventListener('change', () => {
      const preview = document.querySelector('[data-color-preview]');
      let image = preview.querySelector('img');
      const placeholder = preview.querySelector('.product-object');
      if (input.dataset.colorPhoto) {
        if (!image) {
          image = document.createElement('img');
          image.className = 'product-photo';
          preview.prepend(image);
        }
        image.src = input.dataset.colorPhoto;
        image.alt = `${document.querySelector('h1').textContent} — ${input.value}`;
        image.hidden = false;
        if (placeholder) placeholder.hidden = true;
      } else {
        if (image) image.hidden = true;
        if (placeholder) placeholder.hidden = false;
      }
    });
  });
  document.querySelectorAll('[data-variant-sale]').forEach(form => {
    const product = form.querySelector('[data-variant-product]');
    const size = form.querySelector('[data-variant-size]');
    const color = form.querySelector('[data-variant-color]');
    const fill = (select, values) => {
      select.replaceChildren(new Option(values.length ? 'Choose option' : 'Standard / no variation', ''));
      values.forEach(value => select.add(new Option(value, value)));
      select.required = values.length > 0;
    };
    const update = () => {
      const option = product.selectedOptions[0];
      fill(size, (option?.dataset.sizes || '').split(',').map(s => s.trim()).filter(Boolean));
      fill(color, JSON.parse(option?.dataset.colors || '[]').map(c => c.name));
    };
    product.addEventListener('change', update);
    update();
    const allocation = form.querySelector('[name=allocation_id]');
    if (allocation) allocation.addEventListener('change', () => {
      const option = allocation.selectedOptions[0];
      if (!option.value) return;
      form.querySelector('[name=agent_id]').value = option.dataset.agent;
      product.value = option.dataset.product;
      product.dispatchEvent(new Event('change'));
      // Saved allocations remain valid even if catalog variant names later change.
      if (![...size.options].some(o => o.value === option.dataset.size)) size.add(new Option(option.dataset.size, option.dataset.size));
      if (![...color.options].some(o => o.value === option.dataset.color)) color.add(new Option(option.dataset.color, option.dataset.color));
      size.value = option.dataset.size;
      color.value = option.dataset.color;
      form.querySelector('[name=company_discount_percent]').value = option.dataset.discount;
    });
  });
});