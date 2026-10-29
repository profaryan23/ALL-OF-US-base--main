document.addEventListener('DOMContentLoaded', () => {
  // Color Editor in Inventory Admin
  document.querySelectorAll('[data-color-editor]').forEach(editor => {
    const rows = editor.querySelector('[data-color-rows]');
    if (!rows) return;
    const countDisplay = editor.querySelector('.color-count-num');
    
    const updateCount = () => {
      if (countDisplay) {
        countDisplay.textContent = rows.querySelectorAll('.color-editor-card').length;
      }
    };

    const reindex = () => {
      rows.querySelectorAll('.color-editor-card').forEach((card, i) => {
        const fileInput = card.querySelector('input[type=file]');
        if (fileInput) fileInput.name = `color_photo_${i}`;
        const existingInput = card.querySelector('input[name^="color_existing_photo"]');
        if (existingInput) existingInput.name = `color_existing_photo_${i}`;
        const removeCheck = card.querySelector('input[name^="remove_color_photo"]');
        if (removeCheck) removeCheck.name = `remove_color_photo_${i}`;
      });
      updateCount();
    };

    const addColorCard = (name, hex) => {
      if (rows.children.length >= 20) {
        alert("Maximum 20 colors allowed per product.");
        return;
      }
      const existingNames = Array.from(rows.querySelectorAll('.color-name-input')).map(input => input.value.trim().toLowerCase());
      if (existingNames.includes(name.trim().toLowerCase())) {
        alert(`Color "${name}" is already in the list.`);
        return;
      }
      const card = document.createElement('div');
      card.className = 'color-editor-card';
      const idx = rows.children.length;
      card.innerHTML = `
        <div class="color-card-top">
          <div class="color-card-swatch-wrap">
            <span class="color-swatch-badge" style="background: ${hex};"></span>
            <input type="color" name="color_hex" value="${hex}" class="color-hex-picker" title="Change swatch color">
          </div>
          <div class="color-card-name-wrap">
            <input name="color_name" maxlength="60" value="${name}" placeholder="Color name" required class="color-name-input">
            <input type="hidden" name="color_existing_photo_${idx}" value="">
          </div>
          <button type="button" class="button-remove-color" data-remove-color title="Remove this color">✕</button>
        </div>
        <div class="color-card-photo-row">
          <div class="color-photo-thumb-wrap empty-thumb">
            <span>No photo</span>
          </div>
          <div class="color-photo-actions">
            <span class="photo-status-tag empty">Upload photo for this color</span>
            <label class="btn-file-subtle">
              Upload photo
              <input type="file" name="color_photo_${idx}" accept="image/jpeg,image/png,image/webp">
            </label>
          </div>
        </div>
      `;
      rows.appendChild(card);
      reindex();
    };

    // Preset color buttons
    editor.querySelectorAll('.color-preset-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        e.preventDefault();
        const name = pill.dataset.presetName;
        const hex = pill.dataset.presetHex;
        addColorCard(name, hex);
      });
    });

    // Custom color adder
    const btnCustom = editor.querySelector('.btn-add-custom-color');
    const inputCustomName = editor.querySelector('.custom-color-name-input');
    const inputCustomPicker = editor.querySelector('.custom-color-picker-input');
    if (btnCustom && inputCustomName && inputCustomPicker) {
      btnCustom.addEventListener('click', (e) => {
        e.preventDefault();
        const name = inputCustomName.value.trim();
        if (!name) {
          inputCustomName.focus();
          return;
        }
        addColorCard(name, inputCustomPicker.value);
        inputCustomName.value = '';
      });
    }

    // Dynamic swatch color sync
    editor.addEventListener('input', event => {
      if (event.target.classList.contains('color-hex-picker')) {
        const badge = event.target.closest('.color-card-swatch-wrap')?.querySelector('.color-swatch-badge');
        if (badge) {
          badge.style.backgroundColor = event.target.value;
        }
      }
    });

    // Remove color button
    editor.addEventListener('click', event => {
      if (event.target.matches('[data-remove-color]')) {
        event.preventDefault();
        event.target.closest('.color-editor-card').remove();
        reindex();
      }
    });
  });

  // Preview swatch clicks in Storefront Preview Box
  document.querySelectorAll('.preview-swatch-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const targetId = chip.dataset.previewTarget;
      const photoUrl = chip.dataset.photoUrl;
      const img = document.getElementById(targetId);
      if (img && photoUrl) {
        img.src = photoUrl;
      }
      const parent = chip.closest('.preview-swatches-bar');
      if (parent) {
        parent.querySelectorAll('.preview-swatch-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
      }
    });
  });

  // Single product detail page photo switcher
  document.querySelectorAll('[data-color-photo]').forEach(input => {
    input.addEventListener('change', () => {
      const preview = document.querySelector('[data-color-preview]');
      if (!preview) return;
      let image = preview.querySelector('img');
      const placeholder = preview.querySelector('.product-object');
      if (input.dataset.colorPhoto) {
        if (!image) {
          image = document.createElement('img');
          image.className = 'product-photo';
          preview.prepend(image);
        }
        image.src = input.dataset.colorPhoto;
        image.alt = `${document.querySelector('h1')?.textContent || ''} — ${input.value}`;
        image.hidden = false;
        if (placeholder) placeholder.hidden = true;
      } else {
        if (image) image.hidden = true;
        if (placeholder) placeholder.hidden = false;
      }
    });
  });

  // Variant sale dropdown logic in agent orders
  document.querySelectorAll('[data-variant-sale]').forEach(form => {
    const product = form.querySelector('[data-variant-product]');
    const size = form.querySelector('[data-variant-size]');
    const color = form.querySelector('[data-variant-color]');
    if (!product || !size || !color) return;
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
  });
});
