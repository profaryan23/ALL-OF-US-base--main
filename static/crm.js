/**
 * ALL OF US STUDIO · CRM MODULE JAVASCRIPT (crm.js)
 * Full interactivity: Cross-filtering, SVGs, Modals, Bulk Actions & Slide-Over Panel
 */

(function () {
  'use strict';

  // --- Central State ---
  const state = {
    csrfToken: '',
    window: '30D',
    startDate: '',
    endDate: '',
    activeSegment: 'all',
    channel: '',
    acquisitionType: '',
    spendBracket: '',
    optIn: '',
    tag: '',
    q: '',
    vennRegion: '',
    vennSegA: '',
    vennSegB: '',
    selectedCustomerIds: new Set(),
    scope: 'selected', // 'selected' | 'filtered'
    activeCustomerId: null,
    customersList: [],
    totalMatching: 0,
    currentPage: 1,
    perPage: 12,
    hasMore: false,
    undoToken: null,
    undoTimer: null,
  };

  // --- Utility Functions ---
  function $(selector, context = document) {
    return context.querySelector(selector);
  }
  function $$(selector, context = document) {
    return Array.from(context.querySelectorAll(selector));
  }

  function getCsrfToken() {
    const meta = $('input[name="csrf_token"]');
    return meta ? meta.value : (state.csrfToken || '');
  }

  function formatMoney(amount) {
    const num = parseFloat(amount) || 0;
    return 'Rs ' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // --- Sync URL Params ---
  function updateUrlParams() {
    const params = new URLSearchParams();
    if (state.window && state.window !== '30D') params.set('window', state.window);
    if (state.startDate) params.set('start_date', state.startDate);
    if (state.endDate) params.set('end_date', state.endDate);
    if (state.activeSegment && state.activeSegment !== 'all') params.set('segment_id', state.activeSegment);
    if (state.channel) params.set('channel', state.channel);
    if (state.acquisitionType) params.set('acquisition_type', state.acquisitionType);
    if (state.spendBracket) params.set('spend_bracket', state.spendBracket);
    if (state.optIn) params.set('opt_in', state.optIn);
    if (state.tag) params.set('tag', state.tag);
    if (state.q) params.set('q', state.q);
    if (state.vennRegion) {
      params.set('venn_region', state.vennRegion);
      params.set('venn_a', state.vennSegA);
      params.set('venn_b', state.vennSegB);
    }
    const qs = params.toString();
    const newUrl = window.location.pathname + (qs ? '?' + qs : '');
    window.history.replaceState({}, '', newUrl);
  }

  function readInitialParams() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('window')) state.window = params.get('window');
    if (params.get('start_date')) state.startDate = params.get('start_date');
    if (params.get('end_date')) state.endDate = params.get('end_date');
    if (params.get('segment_id')) state.activeSegment = params.get('segment_id');
    if (params.get('channel')) state.channel = params.get('channel');
    if (params.get('acquisition_type')) state.acquisitionType = params.get('acquisition_type');
    if (params.get('spend_bracket')) state.spendBracket = params.get('spend_bracket');
    if (params.get('opt_in')) state.optIn = params.get('opt_in');
    if (params.get('tag')) state.tag = params.get('tag');
    if (params.get('q')) state.q = params.get('q');
    if (params.get('venn_region')) {
      state.vennRegion = params.get('venn_region');
      state.vennSegA = params.get('venn_a') || '';
      state.vennSegB = params.get('venn_b') || '';
    }
  }

  // --- Fetch & Render Customers Ledger ---
  async function loadCustomers(append = false) {
    if (!append) {
      state.currentPage = 1;
    }
    const params = new URLSearchParams({
      page: state.currentPage,
      per_page: state.perPage,
    });
    if (state.q) params.set('q', state.q);
    if (state.channel) params.set('channel', state.channel);
    if (state.acquisitionType) params.set('acquisition_type', state.acquisitionType);
    if (state.spendBracket) params.set('spend_bracket', state.spendBracket);
    if (state.optIn) params.set('opt_in', state.optIn);
    if (state.tag) params.set('tag', state.tag);
    if (state.activeSegment && state.activeSegment !== 'all') params.set('segment_id', state.activeSegment);
    if (state.vennRegion) {
      params.set('venn_region', state.vennRegion);
      params.set('venn_a', state.vennSegA);
      params.set('venn_b', state.vennSegB);
    }

    try {
      const res = await fetch(`/admin/crm/api/customers?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to load customers');
      const data = await res.json();

      state.totalMatching = data.total_matching;
      state.hasMore = data.has_more;

      if (append) {
        state.customersList = state.customersList.concat(data.customers);
      } else {
        state.customersList = data.customers;
      }

      renderCustomerTable(append);
      renderActiveChips();
      updateUrlParams();
      updateBulkBar();
    } catch (err) {
      console.error('Error loading customers:', err);
    }
  }

  function renderCustomerTable(append = false) {
    const tbody = $('#crm-table-body');
    if (!tbody) return;

    if (!append) {
      tbody.innerHTML = '';
    }

    if (state.customersList.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="table-empty" style="text-align: center; padding: 36px 14px; color: #888;">No customers match the active filters or search criteria.</td></tr>`;
      const showMoreBtn = $('#crm-show-more-btn');
      if (showMoreBtn) showMoreBtn.style.display = 'none';
      const counter = $('#crm-pagination-counter');
      if (counter) counter.textContent = 'Showing 0 of 0 customers';
      return;
    }

    const startIdx = append ? (state.currentPage - 1) * state.perPage : 0;
    const slice = state.customersList.slice(startIdx);

    slice.forEach(c => {
      const tr = document.createElement('tr');
      tr.id = `crm-row-${c.id}`;
      tr.className = state.selectedCustomerIds.has(c.id) ? 'selected' : '';
      if (state.activeCustomerId === c.id) tr.classList.add('active-row');

      const isSubscribed = c.marketing_opt_in;
      const statusClass = c.marketing_status === 'subscribed' ? 'subscribed' : (c.marketing_status === 'unsubscribed' ? 'unsubscribed' : 'not_opted_in');
      const statusLabel = c.marketing_status === 'subscribed' ? 'Subscribed' : (c.marketing_status === 'unsubscribed' ? 'Unsubscribed' : 'Not opted-in');

      const tagsHtml = (c.tags || []).map(t => `<span class="crm-tag-chip" onclick="window.crmFilterByTag('${escapeHtml(t)}', event)">${escapeHtml(t)}</span>`).join('');

      tr.innerHTML = `
        <td style="width: 32px; text-align: center;" onclick="event.stopPropagation()">
          <input type="checkbox" class="crm-row-cb" data-customer-id="${c.id}" ${state.selectedCustomerIds.has(c.id) ? 'checked' : ''}>
        </td>
        <td onclick="window.crmOpenCustomerDetail(${c.id})">
          <div class="crm-cust-cell">
            <div class="crm-avatar">${escapeHtml(c.first_name[0] || 'C')}${escapeHtml(c.last_name[0] || '')}</div>
            <div class="crm-cust-meta">
              <strong>${escapeHtml(c.name)} <span class="crm-badge crm-badge-rank">${escapeHtml(c.rank)}</span></strong>
              <small>Agent: ${escapeHtml(c.agent_names || 'Direct sales')}</small>
            </div>
          </div>
        </td>
        <td onclick="window.crmOpenCustomerDetail(${c.id})">
          <div style="font-weight: 500;">${escapeHtml(c.email)}</div>
          <small style="color: #777;">${escapeHtml(c.phone || 'No phone')}</small>
        </td>
        <td onclick="window.crmOpenCustomerDetail(${c.id})">
          <span class="crm-badge crm-badge-channel" style="margin-right: 4px;">${escapeHtml(c.channel)}</span>
          <span class="crm-badge crm-badge-type">${escapeHtml(c.acquisition_type)}</span>
          ${tagsHtml ? `<div style="margin-top: 4px;">${tagsHtml}</div>` : ''}
        </td>
        <td onclick="window.crmOpenCustomerDetail(${c.id})">
          ${escapeHtml(c.joined_date)}
        </td>
        <td onclick="window.crmOpenCustomerDetail(${c.id})" style="font-weight: 600;">
          ${c.order_count}
        </td>
        <td onclick="window.crmOpenCustomerDetail(${c.id})" style="font-weight: 700; color: #111;">
          ${formatMoney(c.spend)}
        </td>
        <td onclick="window.crmOpenCustomerDetail(${c.id})">
          <span class="crm-status-pill ${statusClass}">
            <span style="font-size: 8px;">●</span> ${statusLabel}
          </span>
        </td>
      `;

      tbody.appendChild(tr);
    });

    // Update Show More Button and Counter
    const showMoreBtn = $('#crm-show-more-btn');
    if (showMoreBtn) {
      showMoreBtn.style.display = state.hasMore ? 'inline-block' : 'none';
    }
    const counter = $('#crm-pagination-counter');
    if (counter) {
      counter.textContent = `Showing ${state.customersList.length} of ${state.totalMatching} customers`;
    }

    // Attach checkbox handlers
    $$('.crm-row-cb', tbody).forEach(cb => {
      cb.addEventListener('change', function (e) {
        const id = parseInt(this.dataset.customerId, 10);
        if (this.checked) {
          state.selectedCustomerIds.add(id);
          this.closest('tr').classList.add('selected');
        } else {
          state.selectedCustomerIds.delete(id);
          this.closest('tr').classList.remove('selected');
        }
        updateBulkBar();
      });
    });
  }

  // --- Render Active Filter Chips ---
  function renderActiveChips() {
    const container = $('#crm-active-chips-bar');
    if (!container) return;

    const chips = [];

    if (state.activeSegment && state.activeSegment !== 'all') {
      const activeTab = $(`.crm-tab-item[data-segment-id="${state.activeSegment}"]`);
      const name = activeTab ? activeTab.dataset.segmentName : `Segment #${state.activeSegment}`;
      chips.push({ type: 'segment', label: `Segment: ${name}`, clear: () => window.crmSelectSegment('all') });
    }
    if (state.channel) {
      chips.push({ type: 'channel', label: `Channel: ${state.channel}`, clear: () => { state.channel = ''; loadCustomers(); } });
    }
    if (state.acquisitionType) {
      chips.push({ type: 'acquisitionType', label: `Type: ${state.acquisitionType}`, clear: () => { state.acquisitionType = ''; loadCustomers(); } });
    }
    if (state.spendBracket) {
      chips.push({ type: 'spendBracket', label: `Bracket: ${state.spendBracket}`, clear: () => { state.spendBracket = ''; loadCustomers(); } });
    }
    if (state.optIn) {
      chips.push({ type: 'optIn', label: `Consent: ${state.optIn}`, clear: () => { state.optIn = ''; loadCustomers(); } });
    }
    if (state.tag) {
      chips.push({ type: 'tag', label: `Tag: ${state.tag}`, clear: () => { state.tag = ''; loadCustomers(); } });
    }
    if (state.q) {
      chips.push({ type: 'q', label: `Search: "${state.q}"`, clear: () => { state.q = ''; const inp = $('#crm-search-input'); if (inp) inp.value = ''; loadCustomers(); } });
    }
    if (state.vennRegion) {
      const regionNames = { only_a: 'Only Segment A', both: 'Overlap (Both)', only_b: 'Only Segment B' };
      chips.push({ type: 'venn', label: `Venn: ${regionNames[state.vennRegion] || state.vennRegion}`, clear: () => { state.vennRegion = ''; loadCustomers(); } });
    }

    if (chips.length === 0) {
      container.innerHTML = '';
      container.classList.remove('has-filters');
      return;
    }

    container.classList.add('has-filters');
    container.innerHTML = `
      <span style="font-weight: 600; font-size: 10px; color: #777; text-transform: uppercase;">Active Filters:</span>
      ${chips.map((ch, idx) => `
        <span class="crm-chip">
          ${escapeHtml(ch.label)}
          <button type="button" class="crm-chip-remove" data-chip-idx="${idx}">✕</button>
        </span>
      `).join('')}
      <span style="margin-left: auto; color: #555; font-size: 10.5px;">Matches: <strong>${state.totalMatching}</strong></span>
      <a href="javascript:void(0)" class="crm-clear-all-link" id="crm-clear-all-chips">Clear all</a>
    `;

    $$('.crm-chip-remove', container).forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.chipIdx, 10);
        if (chips[idx] && chips[idx].clear) chips[idx].clear();
      });
    });

    const clearAll = $('#crm-clear-all-chips', container);
    if (clearAll) {
      clearAll.addEventListener('click', () => {
        state.activeSegment = 'all');
        state.channel = '';
        state.acquisitionType = '';
        state.spendBracket = '';
        state.optIn = '';
        state.tag = '';
        state.q = '';
        state.vennRegion = '';
        const searchInput = $('#crm-search-input');
        if (searchInput) searchInput.value = '';
        $$('.crm-tab-item').forEach(t => t.classList.toggle('active', t.dataset.segmentId === 'all'));
        loadCustomers();
      });
    }
  }

  // --- Sticky Bulk Actions Bar ---
  function updateBulkBar() {
    const bar = $('#crm-sticky-bulk-bar');
    if (!bar) return;

    const count = state.selectedCustomerIds.size;
    if (count > 0) {
      bar.classList.add('visible');
      const counterEl = $('#crm-bulk-count-el');
      if (counterEl) {
        counterEl.textContent = `${count} customer${count > 1 ? 's' : ''} selected`;
      }
      const scopeSelBtn = $('#crm-scope-selected-btn');
      const scopeFiltBtn = $('#crm-scope-filtered-btn');
      if (scopeSelBtn) scopeSelBtn.textContent = `Selected (${count})`;
      if (scopeFiltBtn) scopeFiltBtn.textContent = `All Matching (${state.totalMatching})`;
    } else {
      bar.classList.remove('visible');
    }
  }

  // --- Toast Notification ---
  function showToast(message, undoAction = null) {
    const toast = $('#crm-toast');
    if (!toast) return;
    toast.innerHTML = `
      <span>${escapeHtml(message)}</span>
      ${undoAction ? `<span class="crm-toast-undo" id="crm-toast-undo-btn">Undo Action</span>` : ''}
    `;
    toast.classList.add('visible');

    if (undoAction) {
      const undoBtn = $('#crm-toast-undo-btn');
      if (undoBtn) {
        undoBtn.onclick = () => {
          undoAction();
          toast.classList.remove('visible');
        };
      }
    }

    if (state.undoTimer) clearTimeout(state.undoTimer);
    state.undoTimer = setTimeout(() => {
      toast.classList.remove('visible');
    }, 10000);
  }

  // --- Slide-Over Customer Detail Panel ---
  window.crmOpenCustomerDetail = async function (customerId) {
    state.activeCustomerId = customerId;
    const panel = $('#crm-slide-panel');
    const backdrop = $('#crm-slide-backdrop');
    if (!panel || !backdrop) return;

    panel.classList.add('open');
    backdrop.classList.add('open');

    // Highlight row in table
    $$('#crm-table-body tr').forEach(r => r.classList.remove('active-row'));
    const activeRow = $(`#crm-row-${customerId}`);
    if (activeRow) activeRow.classList.add('active-row');

    try {
      const res = await fetch(`/admin/crm/api/customer/${customerId}`);
      if (!res.ok) throw new Error('Customer not found');
      const data = await res.json();
      renderCustomerDetailPanel(data);
    } catch (err) {
      console.error('Error fetching customer detail:', err);
    }
  };

  window.crmCloseCustomerDetail = function () {
    const panel = $('#crm-slide-panel');
    const backdrop = $('#crm-slide-backdrop');
    if (panel) panel.classList.remove('open');
    if (backdrop) backdrop.classList.remove('open');
    state.activeCustomerId = null;
    $$('#crm-table-body tr').forEach(r => r.classList.remove('active-row'));
  };

  function renderCustomerDetailPanel(data) {
    const container = $('#crm-slide-panel-body');
    if (!container) return;

    const initials = (data.first_name[0] || 'C') + (data.last_name[0] || '');
    const segmentsHtml = (data.segments || []).map(s => `
      <span class="crm-badge" style="background: ${s.color}22; color: ${s.color}; border: 1px solid ${s.color}44; margin-right: 4px;">
        ● ${escapeHtml(s.name)}
      </span>
    `).join('');

    const tagsHtml = (data.tags || []).map(t => `
      <span class="crm-chip" style="margin: 2px;">
        ${escapeHtml(t)}
        <button type="button" class="crm-chip-remove" onclick="window.crmRemoveTagFromCustomer(${data.id}, '${escapeHtml(t)}')">✕</button>
      </span>
    `).join('');

    // Spend history sparkline
    const maxMonthSpend = Math.max(...(data.spend_history.map(s => s.spend)), 100);
    const sparklineBars = data.spend_history.map(s => {
      const heightPercent = Math.max(4, Math.round((s.spend / maxMonthSpend) * 100));
      return `
        <div class="crm-spark-col" title="${s.label}: Rs ${s.spend.toFixed(2)} (${s.orders} orders)">
          <div class="crm-spark-bar" style="height: ${heightPercent}%;"></div>
          <span>${s.label}</span>
        </div>
      `;
    }).join('');

    // Timeline groups HTML
    const timelineHtml = (data.timeline_groups || []).map(group => `
      <div class="crm-timeline-day-group">
        <div class="crm-day-label">${escapeHtml(group.date_label)}</div>
        ${group.items.map(item => {
          let icon = '📝';
          if (item.type === 'order') icon = '📦';
          else if (item.type === 'call') icon = '📞';
          else if (item.type === 'email') icon = '✉️';
          else if (item.type === 'store_visit') icon = '🏪';
          else if (item.type === 'system') icon = '⚙️';

          return `
            <div class="crm-timeline-item" data-category="${item.category}">
              <div class="crm-timeline-icon">${icon}</div>
              <div class="crm-timeline-body">
                <div class="crm-timeline-title-row">
                  <span class="crm-timeline-title">${escapeHtml(item.title)}</span>
                  <span class="crm-timeline-time">${escapeHtml(item.time_str)}</span>
                </div>
                <p class="crm-timeline-text">${escapeHtml(item.content)}</p>
                <small style="color: #888; font-size: 8.5px; margin-top: 2px;">Logged by ${escapeHtml(item.author)}</small>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `).join('');

    container.innerHTML = `
      <!-- Header Area -->
      <div class="crm-panel-header">
        <div class="crm-panel-profile">
          <div class="crm-panel-avatar">${escapeHtml(initials)}</div>
          <div>
            <h2>${escapeHtml(data.name)} <span class="crm-badge crm-badge-rank">${escapeHtml(data.rank)}</span></h2>
            <div class="crm-panel-contact">
              <a href="mailto:${escapeHtml(data.email)}">${escapeHtml(data.email)}</a>
              ${data.phone ? `<span>·</span> <a href="tel:${escapeHtml(data.phone)}">${escapeHtml(data.phone)}</a>` : ''}
            </div>
            ${segmentsHtml ? `<div style="margin-top: 6px;">${segmentsHtml}</div>` : ''}
          </div>
        </div>
        <button type="button" class="crm-panel-close" onclick="window.crmCloseCustomerDetail()" title="Close (Esc)">✕</button>
      </div>

      <div class="crm-panel-content">
        <!-- Quick Action Trigger Buttons -->
        <div style="display: flex; gap: 8px;">
          ${data.phone ? `<a href="tel:${escapeHtml(data.phone)}" class="crm-btn-secondary" style="flex: 1; justify-content: center;">📞 Call</a>` : ''}
          <a href="mailto:${escapeHtml(data.email)}" class="crm-btn-secondary" style="flex: 1; justify-content: center;">✉️ Email</a>
          <button type="button" class="crm-btn-secondary" style="flex: 1; justify-content: center;" onclick="document.getElementById('crm-quicklog-input').focus()">📝 + Note</button>
        </div>

        <!-- 6-Month Spend Progression & Key Metrics -->
        <div class="crm-spend-spark-box">
          <div class="crm-spend-spark-head">
            <span style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: #555;">6-Month Spend Velocity</span>
            <strong style="font-size: 12px; color: #111;">Total: ${formatMoney(data.metrics.ltv)}</strong>
          </div>
          <div class="crm-spend-spark-bars">
            ${sparklineBars}
          </div>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 12px; text-align: center;">
            <div style="background: #faf9f5; padding: 6px; border-radius: 3px;">
              <small style="font-size: 8px; text-transform: uppercase; color: #777;">Avg Order (AOV)</small>
              <strong style="display: block; font-size: 11px;">${formatMoney(data.metrics.aov)}</strong>
            </div>
            <div style="background: #faf9f5; padding: 6px; border-radius: 3px;">
              <small style="font-size: 8px; text-transform: uppercase; color: #777;">Completed Orders</small>
              <strong style="display: block; font-size: 11px;">${data.metrics.order_count}</strong>
            </div>
            <div style="background: #faf9f5; padding: 6px; border-radius: 3px;">
              <small style="font-size: 8px; text-transform: uppercase; color: #777;">Last Order</small>
              <strong style="display: block; font-size: 10px;">${escapeHtml(data.metrics.last_order_date)}</strong>
            </div>
          </div>
        </div>

        <!-- Tags Management Strip -->
        <div style="background: #fff; border: 1px solid var(--crm-line); padding: 12px; border-radius: 4px;">
          <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
            <span style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: #555;">Customer Tags</span>
          </div>
          <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 4px;">
            ${tagsHtml}
            <div style="display: inline-flex; gap: 4px; margin-left: 4px;">
              <input type="text" id="crm-new-tag-input" placeholder="+ Tag" style="padding: 2px 6px; font-size: 9.5px; border: 1px solid #ccc; border-radius: 2px; width: 65px;">
              <button type="button" class="crm-btn-secondary" style="padding: 2px 6px; font-size: 9.5px;" onclick="window.crmAddTagToCustomer(${data.id})">Add</button>
            </div>
          </div>
        </div>

        <!-- Vertical Interaction Timeline -->
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #222;">Interaction History</span>
            <!-- Category Filter Pills -->
            <div style="display: flex; gap: 4px; font-size: 9px;" id="crm-timeline-filter-pills">
              <button type="button" class="crm-quicklog-tab active" data-cat="all">All (${data.category_counts.all})</button>
              <button type="button" class="crm-quicklog-tab" data-cat="orders">Orders (${data.category_counts.orders})</button>
              <button type="button" class="crm-quicklog-tab" data-cat="notes">Notes (${data.category_counts.notes})</button>
              <button type="button" class="crm-quicklog-tab" data-cat="contact">Contact (${data.category_counts.contact})</button>
              <button type="button" class="crm-quicklog-tab" data-cat="system">System (${data.category_counts.system})</button>
            </div>
          </div>

          <!-- Quick Log Box -->
          <div class="crm-quicklog-box" style="margin-bottom: 14px;">
            <div class="crm-quicklog-tabs">
              <button type="button" class="crm-quicklog-tab active" data-log-type="note">📝 Team Note</button>
              <button type="button" class="crm-quicklog-tab" data-log-type="call">📞 Call Log</button>
              <button type="button" class="crm-quicklog-tab" data-log-type="email">✉️ Email Log</button>
            </div>
            <textarea id="crm-quicklog-input" class="crm-quicklog-input" placeholder="Type interaction details, conversation note, or touchpoint log..."></textarea>
            <div style="display: flex; justify-content: flex-end;">
              <button type="button" class="crm-btn-primary" onclick="window.crmPostInteraction(${data.id})">Post Entry</button>
            </div>
          </div>

          <!-- Grouped Events List -->
          <div class="crm-timeline-v" id="crm-timeline-list-wrap">
            ${timelineHtml || '<div style="text-align: center; color: #888; padding: 20px;">No timeline entries logged yet.</div>'}
          </div>
        </div>
      </div>
    `;

    // Timeline tab filtering
    $$('#crm-timeline-filter-pills .crm-quicklog-tab').forEach(btn => {
      btn.addEventListener('click', function () {
        $$('#crm-timeline-filter-pills .crm-quicklog-tab').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        const cat = this.dataset.cat;
        $$('.crm-timeline-item').forEach(item => {
          if (cat === 'all' || item.dataset.category === cat) {
            item.style.display = 'flex';
          } else {
            item.style.display = 'none';
          }
        });
      });
    });

    // Quick log type selector
    $$('.crm-quicklog-box .crm-quicklog-tabs .crm-quicklog-tab').forEach(btn => {
      btn.addEventListener('click', function () {
        $$('.crm-quicklog-box .crm-quicklog-tabs .crm-quicklog-tab').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
      });
    });
  }

  // --- Quick-Log Interaction Post ---
  window.crmPostInteraction = async function (customerId) {
    const input = $('#crm-quicklog-input');
    const content = input ? input.value.trim() : '';
    if (!content) return alert('Please enter note or interaction text.');

    const activeTypeTab = $('.crm-quicklog-box .crm-quicklog-tab.active');
    const type = activeTypeTab ? activeTypeTab.dataset.logType : 'note';

    try {
      const res = await fetch(`/admin/crm/api/customer/${customerId}/interaction`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({ type, content }),
      });
      if (!res.ok) throw new Error('Failed to post entry');
      input.value = '';
      window.crmOpenCustomerDetail(customerId);
      showToast('Interaction logged to timeline.');
    } catch (err) {
      alert('Error posting interaction: ' + err.message);
    }
  };

  // --- Add / Remove Tags from Customer ---
  window.crmAddTagToCustomer = async function (customerId) {
    const inp = $('#crm-new-tag-input');
    const tag = inp ? inp.value.trim() : '';
    if (!tag) return;

    try {
      const res = await fetch(`/admin/crm/api/customer/${customerId}/tags`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({ action: 'add', tag }),
      });
      if (!res.ok) throw new Error('Failed to add tag');
      inp.value = '';
      window.crmOpenCustomerDetail(customerId);
      loadCustomers(false);
      showToast(`Added tag "${tag}"`);
    } catch (err) {
      alert(err.message);
    }
  };

  window.crmRemoveTagFromCustomer = async function (customerId, tag) {
    try {
      const res = await fetch(`/admin/crm/api/customer/${customerId}/tags`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({ action: 'remove', tag }),
      });
      if (!res.ok) throw new Error('Failed to remove tag');
      window.crmOpenCustomerDetail(customerId);
      loadCustomers(false);
      showToast(`Removed tag "${tag}"`);
    } catch (err) {
      alert(err.message);
    }
  };

  // --- Keyboard Navigation (J/K cycle, Esc close) ---
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
      return;
    }
    if (e.key === 'Escape') {
      window.crmCloseCustomerDetail();
      window.crmCloseSegmentModal();
      window.crmCloseEmailModal();
      window.crmCloseAddCustomerModal();
      return;
    }

    if (state.activeCustomerId && (e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown')) {
      e.preventDefault();
      const idx = state.customersList.findIndex(c => c.id === state.activeCustomerId);
      if (idx !== -1 && idx < state.customersList.length - 1) {
        window.crmOpenCustomerDetail(state.customersList[idx + 1].id);
      }
    } else if (state.activeCustomerId && (e.key === 'k' || e.key === 'K' || e.key === 'ArrowUp')) {
      e.preventDefault();
      const idx = state.customersList.findIndex(c => c.id === state.activeCustomerId);
      if (idx > 0) {
        window.crmOpenCustomerDetail(state.customersList[idx - 1].id);
      }
    }
  });

  // --- Cross-Filtering Global Triggers ---
  window.crmFilterByChannel = function (channel) {
    if (state.channel === channel) state.channel = '';
    else state.channel = channel;
    highlightDonuts();
    loadCustomers();
  };

  window.crmFilterByAcquisitionType = function (atype) {
    if (state.acquisitionType === atype) state.acquisitionType = '';
    else state.acquisitionType = atype;
    highlightDonuts();
    loadCustomers();
  };

  window.crmFilterBySpendBracket = function (bracketKey) {
    if (state.spendBracket === bracketKey) state.spendBracket = '';
    else state.spendBracket = bracketKey;
    $$('.crm-bracket-row').forEach(row => {
      row.classList.toggle('active', row.dataset.bracketKey === state.spendBracket);
    });
    loadCustomers();
  };

  window.crmFilterByOptIn = function (optInKey) {
    if (state.optIn === optInKey) state.optIn = '';
    else state.optIn = optInKey;
    $$('.crm-optin-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.optinKey === state.optIn);
    });
    loadCustomers();
  };

  window.crmFilterByTag = function (tagName, event) {
    if (event) event.stopPropagation();
    state.tag = tagName;
    loadCustomers();
  };

  window.crmSelectSegment = function (segmentId) {
    state.activeSegment = segmentId;
    $$('.crm-tab-item').forEach(t => {
      t.classList.toggle('active', t.dataset.segmentId === String(segmentId));
    });
    loadCustomers();
  };

  function highlightDonuts() {
    // Channel Donut
    $$('.crm-donut-slice[data-channel]').forEach(sl => {
      if (!state.channel) {
        sl.classList.remove('active', 'fade');
      } else if (sl.dataset.channel === state.channel) {
        sl.classList.add('active');
        sl.classList.remove('fade');
      } else {
        sl.classList.remove('active');
        sl.classList.add('fade');
      }
    });

    // Acquisition Type Donut
    $$('.crm-donut-slice[data-atype]').forEach(sl => {
      if (!state.acquisitionType) {
        sl.classList.remove('active', 'fade');
      } else if (sl.dataset.atype === state.acquisitionType) {
        sl.classList.add('active');
        sl.classList.remove('fade');
      } else {
        sl.classList.remove('active');
        sl.classList.add('fade');
      }
    });
  }

  // --- Head-to-Head Segment Comparison ---
  window.crmToggleCompare = async function () {
    const mod = $('#crm-compare-module');
    if (!mod) return;
    const isOpen = mod.classList.contains('open');
    if (isOpen) {
      mod.classList.remove('open');
    } else {
      mod.classList.add('open');
      loadCompareData();
    }
  };

  window.crmSwapCompare = function () {
    const selA = $('#crm-compare-sel-a');
    const selB = $('#crm-compare-sel-b');
    if (selA && selB) {
      const valA = selA.value;
      selA.value = selB.value;
      selB.value = valA;
      loadCompareData();
    }
  };

  async function loadCompareData() {
    const selA = $('#crm-compare-sel-a');
    const selB = $('#crm-compare-sel-b');
    const segA = selA ? selA.value : 'preset_high_value';
    const segB = selB ? selB.value : 'preset_agent';

    try {
      const res = await fetch(`/admin/crm/api/compare?seg_a=${segA}&seg_b=${segB}`);
      if (!res.ok) throw new Error('Failed to load comparison');
      const data = await res.json();
      renderCompareModule(data);
    } catch (err) {
      console.error('Error loading compare data:', err);
    }
  }

  function renderCompareModule(data) {
    const banner = $('#crm-overlap-banner-wrap');
    if (banner) {
      const riskClass = data.venn.high_overlap_warning ? 'high-risk' : '';
      banner.className = `crm-overlap-banner ${riskClass}`;
      banner.innerHTML = `
        <div>
          <strong>Shared Overlap: ${data.venn.overlap_count} customers</strong>
          <span>(${data.venn.overlap_pct}% overlap) accounting for <strong>${formatMoney(data.venn.shared_revenue)}</strong></span>
          ${data.venn.warning_message ? `<div style="font-size: 10px; margin-top: 3px; font-weight: 600;">${escapeHtml(data.venn.warning_message)}</div>` : ''}
        </div>
        <button type="button" class="crm-btn-primary" style="font-size: 10px;" onclick="window.crmSaveOverlapAsSegment()">Save overlap as segment</button>
      `;
    }

    // Interactive Venn SVG
    const svgWrap = $('#crm-venn-svg-wrap');
    if (svgWrap) {
      const countA = data.stats_a.count;
      const countB = data.stats_b.count;
      const countOverlap = data.venn.overlap_count;

      svgWrap.innerHTML = `
        <svg viewBox="0 0 320 180" class="crm-venn-svg">
          <!-- Left Circle A -->
          <circle cx="110" cy="90" r="65" fill="${data.segment_a.color}" class="crm-venn-circle ${state.vennRegion === 'only_a' ? 'active' : ''}" onclick="window.crmFilterByVenn('only_a', '${escapeHtml(data.segment_a.name)}')"></circle>
          <!-- Right Circle B -->
          <circle cx="210" cy="90" r="65" fill="${data.segment_b.color}" class="crm-venn-circle ${state.vennRegion === 'only_b' ? 'active' : ''}" onclick="window.crmFilterByVenn('only_b', '${escapeHtml(data.segment_b.name)}')"></circle>
          
          <!-- Text Labels -->
          <text x="75" y="95" font-size="13" font-weight="bold" fill="#fff" text-anchor="middle" pointer-events="none">${data.venn.only_a_count}</text>
          <text x="75" y="112" font-size="8.5" fill="#fff" text-anchor="middle" pointer-events="none">Only A</text>
          
          <text x="160" y="95" font-size="14" font-weight="bold" fill="#fff" text-anchor="middle" pointer-events="none">${countOverlap}</text>
          <text x="160" y="112" font-size="8.5" fill="#fff" text-anchor="middle" pointer-events="none">Both</text>
          
          <text x="245" y="95" font-size="13" font-weight="bold" fill="#fff" text-anchor="middle" pointer-events="none">${data.venn.only_b_count}</text>
          <text x="245" y="112" font-size="8.5" fill="#fff" text-anchor="middle" pointer-events="none">Only B</text>

          <text x="110" y="20" font-size="10" font-weight="bold" fill="#111" text-anchor="middle">${escapeHtml(data.segment_a.name)}</text>
          <text x="210" y="20" font-size="10" font-weight="bold" fill="#111" text-anchor="middle">${escapeHtml(data.segment_b.name)}</text>
        </svg>
      `;
    }

    // Comparative Metrics Bars
    const metricsWrap = $('#crm-compare-metrics-wrap');
    if (metricsWrap) {
      const a = data.stats_a;
      const b = data.stats_b;

      const rows = [
        { label: 'Customers', valA: a.count, valB: b.count, fmtA: a.count, fmtB: b.count, max: Math.max(a.count, b.count, 1) },
        { label: 'Total Revenue', valA: a.revenue, valB: b.revenue, fmtA: formatMoney(a.revenue), fmtB: formatMoney(b.revenue), max: Math.max(a.revenue, b.revenue, 1) },
        { label: 'Avg Spend (LTV)', valA: a.ltv, valB: b.ltv, fmtA: formatMoney(a.ltv), fmtB: formatMoney(b.ltv), max: Math.max(a.ltv, b.ltv, 1) },
        { label: 'Avg Order Value (AOV)', valA: a.aov, valB: b.aov, fmtA: formatMoney(a.aov), fmtB: formatMoney(b.aov), max: Math.max(a.aov, b.aov, 1) },
        { label: 'Orders / Customer', valA: a.orders_per_customer, valB: b.orders_per_customer, fmtA: a.orders_per_customer, fmtB: b.orders_per_customer, max: Math.max(a.orders_per_customer, b.orders_per_customer, 1) },
        { label: 'Marketing Opt-in', valA: a.opt_in_rate, valB: b.opt_in_rate, fmtA: a.opt_in_rate + '%', fmtB: b.opt_in_rate + '%', max: 100 },
        { label: 'Repeat Purchase Rate', valA: a.repeat_rate, valB: b.repeat_rate, fmtA: a.repeat_rate + '%', fmtB: b.repeat_rate + '%', max: 100 },
      ];

      metricsWrap.innerHTML = `
        <table class="crm-compare-table">
          <thead>
            <tr>
              <th style="width: 32%;">${escapeHtml(data.segment_a.name)}</th>
              <th style="width: 36%; text-align: center;">Metric</th>
              <th style="width: 32%; text-align: right;">${escapeHtml(data.segment_b.name)}</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(r => `
              <tr>
                <td>
                  <div style="font-weight: 700;">${r.fmtA}</div>
                  <div class="crm-compare-bar-wrap">
                    <div class="crm-comp-bar" style="width: ${Math.round((r.valA / r.max) * 100)}%; background: ${data.segment_a.color};"></div>
                  </div>
                </td>
                <td style="text-align: center; color: #666; font-size: 10px;">${r.label}</td>
                <td style="text-align: right;">
                  <div style="font-weight: 700;">${r.fmtB}</div>
                  <div class="crm-compare-bar-wrap" style="justify-content: flex-end;">
                    <div class="crm-comp-bar" style="width: ${Math.round((r.valB / r.max) * 100)}%; background: ${data.segment_b.color};"></div>
                  </div>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    // Save intersection rules for auto-fill
    window._lastIntersectionRules = data.intersection_rules;
  }

  window.crmFilterByVenn = function (region, segName) {
    const selA = $('#crm-compare-sel-a');
    const selB = $('#crm-compare-sel-b');
    state.vennSegA = selA ? selA.value : '';
    state.vennSegB = selB ? selB.value : '';

    if (state.vennRegion === region) {
      state.vennRegion = '';
    } else {
      state.vennRegion = region;
    }
    loadCustomers();
    loadCompareData();
  };

  window.crmSaveOverlapAsSegment = function () {
    const rules = window._lastIntersectionRules || {};
    window.crmOpenSegmentModal(null, {
      name: 'Overlap: A ∩ B',
      rules: rules,
      color: '#7c3aed',
    });
  };

  // --- Add Customer Modal ---
  window.crmOpenAddCustomerModal = function () {
    const modal = $('#crm-add-customer-modal');
    if (modal) modal.classList.add('open');
    const input = $('#crm-add-first-name');
    if (input) setTimeout(() => input.focus(), 60);
  };

  window.crmCloseAddCustomerModal = function () {
    const modal = $('#crm-add-customer-modal');
    if (modal) modal.classList.remove('open');
  };

  window.crmHandleAddCustomerSubmit = function (event) {
    return true;
  };

  // --- Smart Segment Builder Modal ---
  window.crmOpenSegmentModal = function (segmentId = null, prefillData = null) {
    const modal = $('#crm-segment-modal');
    if (!modal) return;
    modal.classList.add('open');

    const form = $('#crm-segment-form');
    if (!form) return;
    form.reset();

    const idInput = $('#crm-seg-id');
    const nameInput = $('#crm-seg-name');
    const colorInput = $('#crm-seg-color');
    const matchSelect = $('#crm-seg-match');
    const pinCheck = $('#crm-seg-pinned');
    const digestCheck = $('#crm-seg-digest');

    if (segmentId) {
      // Edit existing
      idInput.value = segmentId;
      fetch(`/admin/crm/api/segments`).then(r => r.json()).then(segs => {
        const seg = segs.find(s => s.id === segmentId);
        if (seg) {
          nameInput.value = seg.name;
          colorInput.value = seg.color;
          matchSelect.value = seg.match_type;
          pinCheck.checked = seg.is_pinned;
          digestCheck.checked = seg.daily_digest;
          populateSegmentRulesInForm(seg.rules);
          updateSegmentPreview();
        }
      });
    } else if (prefillData) {
      idInput.value = '';
      nameInput.value = prefillData.name || 'New Segment';
      colorInput.value = prefillData.color || '#111111';
      matchSelect.value = 'all';
      pinCheck.checked = true;
      digestCheck.checked = false;
      populateSegmentRulesInForm(prefillData.rules || {});
      updateSegmentPreview();
    } else {
      idInput.value = '';
      nameInput.value = '';
      colorInput.value = '#111111';
      matchSelect.value = 'all';
      pinCheck.checked = true;
      digestCheck.checked = false;
      updateSegmentPreview();
    }
  };

  window.crmCloseSegmentModal = function () {
    const modal = $('#crm-segment-modal');
    if (modal) modal.classList.remove('open');
  };

  function populateSegmentRulesInForm(rules) {
    // Channel checkboxes
    const channels = rules.channel || [];
    $$('input[name="seg_channel"]').forEach(cb => {
      cb.checked = channels.includes(cb.value);
    });

    // Acquisition Type
    const atypes = rules.acquisition_type || [];
    $$('input[name="seg_atype"]').forEach(cb => {
      cb.checked = atypes.includes(cb.value);
    });

    // Marketing consent
    const mconsent = (rules.marketing_consent && rules.marketing_consent[0]) || 'any';
    const optInRadio = $(`input[name="seg_consent"][value="${mconsent}"]`);
    if (optInRadio) optInRadio.checked = true;

    // Agent
    const agentSel = $('#crm-seg-agent');
    if (agentSel) agentSel.value = rules.agent_id || 'any';

    // Spend
    const minSpend = $('#crm-seg-min-spend');
    const maxSpend = $('#crm-seg-max-spend');
    if (minSpend) minSpend.value = rules.min_spend !== undefined ? rules.min_spend : '';
    if (maxSpend) maxSpend.value = rules.max_spend !== undefined ? rules.max_spend : '';

    // Orders
    const minOrders = $('#crm-seg-min-orders');
    const maxOrders = $('#crm-seg-max-orders');
    if (minOrders) minOrders.value = rules.min_orders !== undefined ? rules.min_orders : '';
    if (maxOrders) maxOrders.value = rules.max_orders !== undefined ? rules.max_orders : '';

    // Days joined
    const maxDays = $('#crm-seg-max-days');
    if (maxDays) maxDays.value = rules.max_days_joined !== undefined ? rules.max_days_joined : '';
  }

  function extractSegmentRulesFromForm() {
    const rules = {};

    const channels = $$('input[name="seg_channel"]:checked').map(c => c.value);
    if (channels.length > 0) rules.channel = channels;

    const atypes = $$('input[name="seg_atype"]:checked').map(c => c.value);
    if (atypes.length > 0) rules.acquisition_type = atypes;

    const consentRadio = $('input[name="seg_consent"]:checked');
    if (consentRadio && consentRadio.value !== 'any') {
      rules.marketing_consent = [consentRadio.value];
    }

    const agentSel = $('#crm-seg-agent');
    if (agentSel && agentSel.value !== 'any') {
      rules.agent_id = agentSel.value;
    }

    const minSpend = $('#crm-seg-min-spend');
    if (minSpend && minSpend.value) rules.min_spend = parseFloat(minSpend.value);
    const maxSpend = $('#crm-seg-max-spend');
    if (maxSpend && maxSpend.value) rules.max_spend = parseFloat(maxSpend.value);

    const minOrders = $('#crm-seg-min-orders');
    if (minOrders && minOrders.value) rules.min_orders = parseInt(minOrders.value, 10);
    const maxOrders = $('#crm-seg-max-orders');
    if (maxOrders && maxOrders.value) rules.max_orders = parseInt(maxOrders.value, 10);

    const maxDays = $('#crm-seg-max-days');
    if (maxDays && maxDays.value) rules.max_days_joined = parseInt(maxDays.value, 10);

    return rules;
  }

  window.crmSeedSegmentFromActiveFilters = function () {
    const rules = {};
    if (state.channel) rules.channel = [state.channel];
    if (state.acquisitionType) rules.acquisition_type = [state.acquisitionType];
    if (state.optIn) rules.marketing_consent = [state.optIn];
    if (state.spendBracket === 'under_50') rules.max_spend = 50;
    else if (state.spendBracket === '50_199') { rules.min_spend = 50; rules.max_spend = 199; }
    else if (state.spendBracket === '200_plus') rules.min_spend = 200;
    else if (state.spendBracket === 'no_spend') rules.max_orders = 0;

    populateSegmentRulesInForm(rules);
    updateSegmentPreview();
    showToast('Applied active table filters to criteria.');
  };

  async function updateSegmentPreview() {
    const rules = extractSegmentRulesFromForm();
    const matchSelect = $('#crm-seg-match');
    const matchType = matchSelect ? matchSelect.value : 'all';

    try {
      const res = await fetch('/admin/crm/api/segments/preview', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({ rules, match_type: matchType }),
      });
      if (!res.ok) return;
      const data = await res.json();

      const countEl = $('#crm-seg-prev-count');
      const shareEl = $('#crm-seg-prev-share');
      const revEl = $('#crm-seg-prev-rev');
      const mixEl = $('#crm-seg-prev-mix');
      const samplesEl = $('#crm-seg-prev-samples');

      if (countEl) countEl.textContent = data.matching_count;
      if (shareEl) shareEl.textContent = `${data.share_percentage}% of customer base`;
      if (revEl) revEl.textContent = formatMoney(data.total_revenue);

      if (mixEl) {
        mixEl.innerHTML = Object.entries(data.channel_mix || {}).map(([k, v]) => `
          <div style="font-size: 9.5px; display: flex; justify-content: space-between; margin: 2px 0;">
            <span>${escapeHtml(k)}</span>
            <strong>${v}%</strong>
          </div>
        `).join('');
      }

      if (samplesEl) {
        samplesEl.innerHTML = (data.sample_customers || []).map(s => `
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #eee; font-size: 10px;">
            <span><strong>${escapeHtml(s.name)}</strong> <small style="color:#777;">(${s.orders} orders)</small></span>
            <strong>${formatMoney(s.spend)}</strong>
          </div>
        `).join('');
      }
    } catch (err) {
      console.error('Error previewing segment:', err);
    }
  }

  // --- Save Smart Segment ---
  window.crmSaveSegmentSubmit = async function (e) {
    if (e) e.preventDefault();

    const idInput = $('#crm-seg-id');
    const nameInput = $('#crm-seg-name');
    const colorInput = $('#crm-seg-color');
    const matchSelect = $('#crm-seg-match');
    const pinCheck = $('#crm-seg-pinned');
    const digestCheck = $('#crm-seg-digest');

    const name = nameInput ? nameInput.value.trim() : '';
    if (!name) return alert('Please enter a segment name.');

    const segmentId = idInput ? idInput.value : '';
    const payload = {
      name: name,
      color: colorInput ? colorInput.value : '#111111',
      match_type: matchSelect ? matchSelect.value : 'all',
      rules: extractSegmentRulesFromForm(),
      is_pinned: pinCheck ? pinCheck.checked : true,
      daily_digest: digestCheck ? digestCheck.checked : false,
    };

    try {
      const url = segmentId ? `/admin/crm/api/segments/${segmentId}` : '/admin/crm/api/segments';
      const method = segmentId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to save smart segment');
      window.crmCloseSegmentModal();
      showToast(`Smart Segment "${name}" saved!`);
      // Reload page to reflect updated tabs and segment badges
      setTimeout(() => window.location.reload(), 400);
    } catch (err) {
      alert(err.message);
    }
  };

  // --- Bulk Email Dispatcher Modal ---
  window.crmOpenEmailModal = function () {
    const modal = $('#crm-email-modal');
    if (!modal) return;

    const count = state.selectedCustomerIds.size;
    if (count === 0) return alert('Please select at least one customer.');

    modal.classList.add('open');

    // Populate recipients preview and check opt-in warnings
    const selectedCustomers = state.customersList.filter(c => state.selectedCustomerIds.has(c.id));
    const nonOptInCount = selectedCustomers.filter(c => !c.marketing_opt_in).length;

    const warnBox = $('#crm-email-warning-box');
    const tmplSelect = $('#crm-email-template-type');

    function updateTemplateWarning() {
      const isMarketing = tmplSelect && tmplSelect.value === 'marketing';
      if (isMarketing && nonOptInCount > 0) {
        warnBox.style.display = 'block';
        warnBox.className = 'crm-overlap-banner high-risk';
        warnBox.innerHTML = `
          ⚠️ <strong>${nonOptInCount} of the ${selectedCustomers.length}</strong> selected recipients have not opted into marketing communications.
          Under privacy regulations, they will be <strong>automatically excluded</strong> from this marketing dispatch.
          <div style="font-size: 10px; margin-top: 2px;">Effective marketing recipients: ${selectedCustomers.length - nonOptInCount}</div>
        `;
      } else {
        warnBox.style.display = 'block';
        warnBox.className = 'crm-overlap-banner';
        warnBox.innerHTML = `
          ℹ️ Service update & operational dispatch: Sent to all <strong>${selectedCustomers.length}</strong> selected recipients.
        `;
      }
    }

    if (tmplSelect) {
      tmplSelect.onchange = updateTemplateWarning;
      updateTemplateWarning();
    }

    // Avatar chips list
    const avatarList = $('#crm-email-recipient-avatars');
    if (avatarList) {
      avatarList.innerHTML = selectedCustomers.slice(0, 10).map(c => `
        <span class="crm-badge" style="background: #eee; margin: 2px;">
          ${escapeHtml(c.name)} ${!c.marketing_opt_in ? '<small style="color:red;">(no consent)</small>' : ''}
        </span>
      `).join('') + (selectedCustomers.length > 10 ? `<span style="font-size: 10px; color: #777;">+${selectedCustomers.length - 10} more</span>` : '');
    }
  };

  window.crmCloseEmailModal = function () {
    const modal = $('#crm-email-modal');
    if (modal) modal.classList.remove('open');
  };

  window.crmInsertVariableTag = function (tag) {
    const bodyInput = $('#crm-email-body-input');
    if (!bodyInput) return;
    const start = bodyInput.selectionStart || 0;
    const end = bodyInput.selectionEnd || 0;
    const text = bodyInput.value;
    bodyInput.value = text.substring(0, start) + tag + text.substring(end);
    bodyInput.focus();
    bodyInput.selectionStart = bodyInput.selectionEnd = start + tag.length;
  };

  window.crmDispatchEmailSubmit = async function () {
    const tmplSelect = $('#crm-email-template-type');
    const subjectInput = $('#crm-email-subject-input');
    const bodyInput = $('#crm-email-body-input');
    const scheduleSelect = $('#crm-email-schedule-select');

    const subject = subjectInput ? subjectInput.value.trim() : '';
    const body = bodyInput ? bodyInput.value.trim() : '';
    if (!body) return alert('Please enter message body.');

    const payload = {
      customer_ids: Array.from(state.selectedCustomerIds),
      template_type: tmplSelect ? tmplSelect.value : 'marketing',
      subject: subject || 'Update from All of Us',
      body: body,
      schedule: scheduleSelect ? scheduleSelect.value : 'immediate',
    };

    try {
      const res = await fetch('/admin/crm/api/bulk/email', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to dispatch emails');
      const data = await res.json();
      window.crmCloseEmailModal();
      showToast(`Dispatched to ${data.sent_count} recipients (${data.excluded_count} excluded).`);
      state.selectedCustomerIds.clear();
      updateBulkBar();
    } catch (err) {
      alert(err.message);
    }
  };

  // --- Bulk Tagging & Consent Operations ---
  window.crmOpenBulkTagPrompt = async function () {
    const tag = prompt('Enter tag to add to selected customers (e.g. VIP, High-Spend, Loyal):');
    if (!tag || !tag.trim()) return;

    try {
      const res = await fetch('/admin/crm/api/bulk/tags', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({
          customer_ids: Array.from(state.selectedCustomerIds),
          action: 'add',
          tag: tag.trim(),
        }),
      });
      if (!res.ok) throw new Error('Bulk tagging failed');
      const data = await res.json();
      loadCustomers();
      showToast(`Added tag "${tag.trim()}" to ${data.affected_count} customers.`, () => {
        window.crmUndoAction(data.undo_token);
      });
    } catch (err) {
      alert(err.message);
    }
  };

  window.crmOpenBulkConsentPrompt = async function () {
    const choice = prompt('Select marketing consent status:\n1 = Subscribed\n2 = Not opted-in\n3 = Unsubscribed', '1');
    if (!choice) return;

    const statusMap = { '1': 'subscribed', '2': 'not_opted_in', '3': 'unsubscribed' };
    const newStatus = statusMap[choice.trim()] || 'subscribed';

    try {
      const res = await fetch('/admin/crm/api/bulk/consent', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({
          customer_ids: Array.from(state.selectedCustomerIds),
          marketing_status: newStatus,
        }),
      });
      if (!res.ok) throw new Error('Bulk consent update failed');
      const data = await res.json();
      loadCustomers();
      showToast(`Updated consent to "${newStatus}" for ${data.affected_count} customers.`, () => {
        window.crmUndoAction(data.undo_token);
      });
    } catch (err) {
      alert(err.message);
    }
  };

  window.crmUndoAction = async function (undoToken) {
    if (!undoToken) return;
    try {
      const res = await fetch('/admin/crm/api/bulk/undo', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify({ undo_token: undoToken }),
      });
      if (!res.ok) throw new Error('Failed to undo action');
      loadCustomers();
      showToast('Action successfully reversed.');
    } catch (err) {
      alert(err.message);
    }
  };

  window.crmExportSelectedCsv = function () {
    const ids = Array.from(state.selectedCustomerIds).join(',');
    if (!ids) {
      // Export all filtered
      window.location.href = `/admin/crm/export?${window.location.search.replace(/^\?/, '')}`;
    } else {
      window.location.href = `/admin/crm/export?ids=${ids}`;
    }
  };

  // --- Initial Setup on DOM Ready ---
  document.addEventListener('DOMContentLoaded', function () {
    state.csrfToken = getCsrfToken();
    readInitialParams();

    // Time window pills
    $$('.crm-time-pill').forEach(pill => {
      pill.addEventListener('click', function () {
        const win = this.dataset.window;
        if (win === 'custom') {
          const panel = $('#crm-custom-date-panel');
          if (panel) panel.classList.toggle('open');
          return;
        }
        state.window = win;
        state.startDate = '';
        state.endDate = '';
        $$('.crm-time-pill').forEach(p => p.classList.toggle('active', p === pill));
        const panel = $('#crm-custom-date-panel');
        if (panel) panel.classList.remove('open');
        updateUrlParams();
        window.location.search = `window=${win}`;
      });
    });

    // Custom date apply
    const applyCustomBtn = $('#crm-apply-custom-date');
    if (applyCustomBtn) {
      applyCustomBtn.addEventListener('click', function () {
        const start = $('#crm-custom-start-date').value;
        const end = $('#crm-custom-end-date').value;
        if (!start) return alert('Select start date.');
        state.window = 'CUSTOM';
        state.startDate = start;
        state.endDate = end;
        window.location.search = `window=CUSTOM&start_date=${start}&end_date=${end}`;
      });
    }

    // Search bar with debounce
    const searchInput = $('#crm-search-input');
    if (searchInput) {
      let debounceTimeout = null;
      searchInput.addEventListener('input', function () {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
          state.q = searchInput.value.trim();
          loadCustomers();
        }, 250);
      });
    }

    // Show more pagination button
    const showMoreBtn = $('#crm-show-more-btn');
    if (showMoreBtn) {
      showMoreBtn.addEventListener('click', function () {
        state.currentPage += 1;
        loadCustomers(true);
      });
    }

    // Master table checkbox
    const masterCb = $('#crm-master-cb');
    if (masterCb) {
      masterCb.addEventListener('change', function () {
        const isChecked = this.checked;
        state.customersList.forEach(c => {
          if (isChecked) state.selectedCustomerIds.add(c.id);
          else state.selectedCustomerIds.delete(c.id);
        });
        $$('.crm-row-cb').forEach(cb => {
          cb.checked = isChecked;
          cb.closest('tr').classList.toggle('selected', isChecked);
        });
        updateBulkBar();
      });
    }

    // Close bulk bar
    const bulkClose = $('#crm-bulk-close-btn');
    if (bulkClose) {
      bulkClose.addEventListener('click', function () {
        state.selectedCustomerIds.clear();
        $$('.crm-row-cb').forEach(cb => {
          cb.checked = false;
          cb.closest('tr').classList.remove('selected');
        });
        if (masterCb) masterCb.checked = false;
        updateBulkBar();
      });
    }

    // Segment form live preview listeners
    const segForm = $('#crm-segment-form');
    if (segForm) {
      segForm.addEventListener('change', updateSegmentPreview);
      segForm.addEventListener('input', updateSegmentPreview);
    }

    // Color swatches in modal
    $$('.crm-color-swatch').forEach(sw => {
      sw.addEventListener('click', function () {
        $$('.crm-color-swatch').forEach(s => s.classList.remove('active'));
        this.classList.add('active');
        const colorInput = $('#crm-seg-color');
        if (colorInput) colorInput.value = this.dataset.color;
      });
    });

    // Initial load
    loadCustomers();
  });

})();

