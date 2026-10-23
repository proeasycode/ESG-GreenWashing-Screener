/**
 * GreenWash-Screener • Vanilla JS Client Application
 * Communicates with FastAPI backend (/api/...)
 */

// =============================================================================
// Application State
// =============================================================================
const state = {
  benchmarkData: null,
  companies: [],
  selectedCompany: null,
  selectedSector: 'all',
  standardsData: null,
  activeFilter: 'all',
  activeCategory: 'all',
  activeTab: 'tab-screener',
  radarSelectedCompanies: ['TSMC', 'NVIDIA', 'Intel', 'GreenTech Corp'],
  
  // LLM Config
  provider: localStorage.getItem('gw_provider') || 'Mock Offline Fallback',
  apiKey: localStorage.getItem('gw_api_key') || '',
  model: localStorage.getItem('gw_model') || '',
  
  // Charts cache
  charts: {
    claimsPie: null,
    standardsBar: null,
    leaderboard: null,
    radar: null,
    talkVsWalk: null,
  }
};

// =============================================================================
// Initialization
// =============================================================================
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupSettingsModal();
  setupFilters();
  setupSectorFilter();
  setupPdfUpload();
  setupClaimTester();
  setupStandardsSearch();

  await checkBackendHealth();
  await loadBenchmarkData();
  await loadStandardsData();
});

// =============================================================================
// Backend Communication
// =============================================================================
async function checkBackendHealth() {
  const pill = document.getElementById('backendStatusPill');
  const dot = pill.querySelector('.status-dot');
  const text = document.getElementById('backendStatusText');

  try {
    const res = await fetch('/api/health');
    if (res.ok) {
      dot.className = 'status-dot connected';
      text.textContent = 'API Connected (FastAPI)';
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    dot.className = 'status-dot error';
    text.textContent = 'Backend Offline';
    console.warn('Backend offline or starting up:', err);
  }
}

async function loadBenchmarkData() {
  try {
    const res = await fetch('/api/benchmark');
    if (!res.ok) throw new Error('Failed to load benchmark data');
    const data = await res.json();
    state.benchmarkData = data;
    state.companies = data.companies || [];

    populateSectorSelector();
    populateCompanySelector();
    renderBenchmarkTab();
  } catch (err) {
    console.error('Error fetching benchmark:', err);
  }
}

function populateSectorSelector() {
  const select = document.getElementById('sectorFilterSelect');
  if (!select) return;

  const currentVal = state.selectedSector || 'all';
  select.innerHTML = '';

  const optAll = document.createElement('option');
  optAll.value = 'all';
  optAll.textContent = `All Sectors (${state.companies.length} companies)`;
  select.appendChild(optAll);

  // Group companies by sector
  const sectorCounts = {};
  state.companies.forEach(c => {
    const s = c.sector || 'Other';
    sectorCounts[s] = (sectorCounts[s] || 0) + 1;
  });

  const sortedSectors = Object.keys(sectorCounts).sort();
  sortedSectors.forEach(sec => {
    const opt = document.createElement('option');
    opt.value = sec;
    opt.textContent = `${sec} (${sectorCounts[sec]})`;
    select.appendChild(opt);
  });

  if (sortedSectors.includes(currentVal) || currentVal === 'all') {
    select.value = currentVal;
  } else {
    select.value = 'all';
    state.selectedSector = 'all';
  }
}

function setupSectorFilter() {
  const select = document.getElementById('sectorFilterSelect');
  const refreshBtn = document.getElementById('refreshBenchmarkBtn');

  if (select) {
    select.addEventListener('change', () => {
      state.selectedSector = select.value;
      renderBenchmarkTab();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.innerHTML = `
        <span class="spinner-sm"></span>
        <span>Refreshing...</span>
      `;
      await loadBenchmarkData();
      refreshBtn.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
        <span>Refresh Benchmark</span>
      `;
    });
  }
}

async function loadStandardsData() {
  try {
    const res = await fetch('/api/standards');
    if (!res.ok) throw new Error('Failed to load standards');
    const data = await res.json();
    state.standardsData = data;
    renderStandardsCorpus(data.standards || []);
  } catch (err) {
    console.error('Error fetching standards:', err);
  }
}

// =============================================================================
// Navigation & Tabs
// =============================================================================
function setupNavigation() {
  const tabLinks = document.querySelectorAll('.tab-link');
  tabLinks.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');
      switchTab(targetId);
    });
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll('.tab-link').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('active', pane.id === tabId);
  });

  // Re-trigger Chart.js resize if benchmark tab is opened
  if (tabId === 'tab-benchmark') {
    setTimeout(() => {
      if (state.charts.leaderboard) state.charts.leaderboard.resize();
      if (state.charts.radar) state.charts.radar.resize();
      if (state.charts.talkVsWalk) state.charts.talkVsWalk.resize();
    }, 50);
  } else if (tabId === 'tab-screener') {
    setTimeout(() => {
      if (state.charts.claimsPie) state.charts.claimsPie.resize();
      if (state.charts.standardsBar) state.charts.standardsBar.resize();
    }, 50);
  }
}

// =============================================================================
// TAB 1: Single-Company Screener
// =============================================================================
function populateCompanySelector() {
  const select = document.getElementById('companySelect');
  if (!select) return;
  const currentVal = select.value;
  select.innerHTML = '';

  state.companies.forEach((comp) => {
    const opt = document.createElement('option');
    opt.value = comp.company;
    const tag = comp.is_custom ? '[Custom] ' : '';
    opt.textContent = `${tag}${comp.company} (${comp.country || ''} &bull; ${comp.sector || ''})`;
    select.appendChild(opt);
  });

  if (currentVal && state.companies.some(c => c.company === currentVal)) {
    select.value = currentVal;
  } else {
    // Select TSMC by default
    const defaultComp = state.companies.find(c => c.company === 'TSMC') || state.companies[0];
    if (defaultComp) {
      select.value = defaultComp.company;
      displayCompanyAudit(defaultComp, defaultComp.is_custom ? 'Custom Audited Report' : 'Benchmark Dataset');
    }
  }

  select.onchange = () => {
    const chosen = state.companies.find(c => c.company === select.value);
    if (chosen) {
      displayCompanyAudit(chosen, chosen.is_custom ? 'Custom Audited Report' : 'Benchmark Dataset');
    }
  };
}

function displayCompanyAudit(company, engineLabel) {
  state.selectedCompany = company;

  // Header and metadata
  document.getElementById('companyHeading').textContent = `${company.company}`;
  document.getElementById('engineTag').textContent = `Assurance Engine: ${engineLabel || 'Heuristic Audit'}`;
  
  const sectorBadge = document.getElementById('companySectorBadge');
  if (sectorBadge) {
    sectorBadge.textContent = `${company.sector || 'Not specified'}`;
  }

  // Explicit Save to Benchmark button
  const saveBtn = document.getElementById('saveBenchmarkExplicitBtn');
  if (saveBtn) {
    saveBtn.classList.remove('hidden');
    saveBtn.innerHTML = company.is_custom 
      ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> <span>In Benchmark</span>`
      : `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> <span>Save to Sector Benchmark</span>`;
    saveBtn.disabled = false;
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
      try {
        const res = await fetch('/api/benchmark/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(company),
        });
        if (!res.ok) throw new Error('Failed to save to benchmark');
        saveBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> <span>Saved to Benchmark</span>`;
        company.is_custom = true;
        await loadBenchmarkData();
      } catch (err) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Error';
        alert(err.message);
      }
    };
  }

  document.getElementById('infoReportTitle').textContent = `${company.report_title || 'Sustainability Report'} (${company.report_year || ''})`;
  document.getElementById('infoSector').textContent = `${company.sector || 'Technology'} | ${company.ticker || 'N/A'}`;
  document.getElementById('infoAssurance').textContent = `${company.assurance_provider || 'None'} (${company.assurance_level || 'None'})`;

  const gwri = company.greenwashing_risk_index || 0;
  const claims = company.claims || [];

  // Risk Badge
  const badgeSlot = document.getElementById('riskBadgeSlot');
  if (gwri <= 48) {
    badgeSlot.innerHTML = `<span class="badge-legit"><span class="badge-dot"></span>VERIFIED / LOW RISK</span>`;
  } else if (gwri <= 74) {
    badgeSlot.innerHTML = `<span class="badge-grey"><span class="badge-dot"></span>INCOMPLETE / GREY ZONE</span>`;
  } else {
    badgeSlot.innerHTML = `<span class="badge-bullshit"><span class="badge-dot"></span>HIGH RISK DISCLOSURES</span>`;
  }

  // KPIs
  document.getElementById('kpiGwri').textContent = `${gwri.toFixed(1)}%`;
  document.getElementById('kpiClaimsCount').textContent = claims.length;

  const legitCount = claims.filter(c => (c.classification === 'legit' || (!c.classification && c.risk_score <= 48))).length;
  const bullshitCount = claims.filter(c => (c.classification === 'bullshit' || (!c.classification && c.risk_score > 74))).length;

  const legitPct = claims.length > 0 ? (legitCount / claims.length) * 100 : 0;
  const bullshitPct = claims.length > 0 ? (bullshitCount / claims.length) * 100 : 0;

  document.getElementById('kpiLegit').textContent = `${legitPct.toFixed(0)}%`;
  document.getElementById('kpiBullshit').textContent = `${bullshitPct.toFixed(0)}%`;
  document.getElementById('kpiScope3').textContent = `${company.scope3_completeness || 0}%`;

  // Update SVG Risk Gauge
  updateRiskGauge(gwri);

  // Update Charts
  renderClaimsPieChart(claims);
  renderStandardsBarChart(company.standard_alignment || {});

  // Populate Category Filter
  populateCategoryFilter(claims);

  // Render Claims Cards
  renderClaimsList(claims);
}

function updateRiskGauge(score) {
  // SVG Needle angle: 0 score = -90 deg, 100 score = +90 deg
  const clampedScore = Math.max(0, Math.min(100, score));
  const angle = -90 + (clampedScore / 100) * 180;
  const needle = document.getElementById('gaugeNeedle');

  // Rotate needle around (100, 110)
  needle.setAttribute('transform', `rotate(${angle} 100 110)`);

  document.getElementById('gaugeScoreText').textContent = `${clampedScore.toFixed(1)}%`;
  const labelEl = document.getElementById('gaugeStatusLabel');
  if (clampedScore <= 30) {
    labelEl.textContent = 'Low Greenwash Risk';
    labelEl.style.color = '#34d399';
  } else if (clampedScore <= 70) {
    labelEl.textContent = 'Grey Zone';
    labelEl.style.color = '#fbbf24';
  } else {
    labelEl.textContent = 'High Greenwash Risk';
    labelEl.style.color = '#fb7185';
  }
}

function renderClaimsPieChart(claims) {
  let legit = 0, grey = 0, bullshit = 0;
  claims.forEach(c => {
    const cls = c.classification || (c.risk_score <= 48 ? 'legit' : (c.risk_score <= 74 ? 'grey' : 'bullshit'));
    if (cls === 'legit') legit++;
    else if (cls === 'grey') grey++;
    else bullshit++;
  });

  const ctx = document.getElementById('claimsPieChart').getContext('2d');
  if (state.charts.claimsPie) state.charts.claimsPie.destroy();

  state.charts.claimsPie = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Verified (Substantiated)', 'Incomplete (Grey Zone)', 'High Risk (Unsubstantiated)'],
      datasets: [{
        data: [legit, grey, bullshit],
        backgroundColor: ['#10b981', '#d97706', '#e11d48'],
        borderWidth: 2,
        borderColor: '#0d1322',
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 }, boxWidth: 10, padding: 12 }
        }
      },
      cutout: '72%'
    }
  });
}

function renderStandardsBarChart(standards) {
  const labels = Object.keys(standards);
  const values = Object.values(standards);

  const ctx = document.getElementById('standardsBarChart').getContext('2d');
  if (state.charts.standardsBar) state.charts.standardsBar.destroy();

  state.charts.standardsBar = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Alignment (%)',
        data: values,
        backgroundColor: '#2563eb',
        borderRadius: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
        },
        x: {
          grid: { display: false },
          ticks: { color: '#cbd5e1', font: { family: 'Inter', size: 11, weight: '500' } }
        }
      },
      plugins: {
        legend: { display: false }
      }
    }
  });
}

function populateCategoryFilter(claims) {
  const select = document.getElementById('claimCategoryFilter');
  const categories = [...new Set(claims.map(c => c.claim_category || 'General'))].sort();

  select.innerHTML = '<option value="all">All Categories</option>';
  categories.forEach(cat => {
    const opt = document.createElement('option');
    opt.value = cat;
    opt.textContent = cat;
    select.appendChild(opt);
  });
}

function setupFilters() {
  const chips = document.querySelectorAll('.filter-chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      chips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.activeFilter = chip.getAttribute('data-filter');
      if (state.selectedCompany) renderClaimsList(state.selectedCompany.claims || []);
    });
  });

  document.getElementById('claimCategoryFilter').addEventListener('change', (e) => {
    state.activeCategory = e.target.value;
    if (state.selectedCompany) renderClaimsList(state.selectedCompany.claims || []);
  });
}

function renderClaimsList(claims) {
  const container = document.getElementById('claimsListContainer');
  container.innerHTML = '';

  const filtered = claims.filter(c => {
    const cls = c.classification || (c.risk_score <= 48 ? 'legit' : (c.risk_score <= 74 ? 'grey' : 'bullshit'));
    const matchFilter = (state.activeFilter === 'all') || (state.activeFilter === cls);
    const cat = c.claim_category || 'General';
    const matchCat = (state.activeCategory === 'all') || (state.activeCategory === cat);
    return matchFilter && matchCat;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div class="card text-center py-6 text-muted">No disclosures match the selected filter criteria.</div>`;
    return;
  }

  filtered.forEach(c => {
    const cls = c.classification || (c.risk_score <= 48 ? 'legit' : (c.risk_score <= 74 ? 'grey' : 'bullshit'));
    const badgeLabel = cls === 'legit' ? 'VERIFIED' : (cls === 'grey' ? 'INCOMPLETE' : 'HIGH RISK');
    const riskScore = c.risk_score !== undefined ? c.risk_score : 50;
    const pScores = c.pillar_scores || { quantification: 50, trajectory: 50, scope: 50, assurance: 50 };

    const card = document.createElement('div');
    card.className = `claim-card ${cls}`;
    card.innerHTML = `
      <div class="claim-header">
        <div>
          <span class="claim-id">Finding ${c.claim_id || 'ID'}</span>
          <span class="claim-page">Page: ${c.page || 'N/A'}</span>
          <span class="claim-category-tag">${c.claim_category || 'General'}</span>
        </div>
        <div>
          <span class="badge-${cls}">${badgeLabel} &bull; Risk ${riskScore.toFixed(0)}%</span>
        </div>
      </div>
      <div class="claim-text">"${c.claim_text}"</div>
      <div class="pillar-chips-row">
        <span class="pillar-chip"><b>Quantification:</b> ${pScores.quantification || 50}% Risk</span>
        <span class="pillar-chip"><b>Roadmap:</b> ${pScores.trajectory || 50}% Risk</span>
        <span class="pillar-chip"><b>Scope:</b> ${pScores.scope || 50}% Risk</span>
        <span class="pillar-chip"><b>Assurance:</b> ${pScores.assurance || 50}% Risk</span>
      </div>
      <div class="claim-verdict-box">
        <b>Standard &amp; Audit Finding:</b> <code>${c.matched_standard || 'ESG Standard'}</code><br>
        ${c.audit_justification || 'Evaluated across multi-pillar regulatory criteria.'}
      </div>
    `;
    container.appendChild(card);
  });
}

// =============================================================================
// Live PDF Upload Mode
// =============================================================================
function setupPdfUpload() {
  const radioDemo = document.getElementById('radioDemoMode');
  const radioPdf = document.getElementById('radioLivePdf');
  const demoSection = document.getElementById('demoSelectorSection');
  const pdfSection = document.getElementById('pdfUploadSection');

  radioDemo.addEventListener('click', () => {
    radioDemo.classList.add('active');
    radioPdf.classList.remove('active');
    demoSection.classList.remove('hidden');
    pdfSection.classList.add('hidden');
    // Restore demo selected company
    const sel = document.getElementById('companySelect');
    const comp = state.companies.find(c => c.company === sel.value);
    if (comp) displayCompanyAudit(comp, 'Benchmark Dataset');
  });

  radioPdf.addEventListener('click', () => {
    radioPdf.classList.add('active');
    radioDemo.classList.remove('active');
    demoSection.classList.add('hidden');
    pdfSection.classList.remove('hidden');
  });

  const dropZone = document.getElementById('pdfDropZone');
  const fileInput = document.getElementById('pdfFileInput');
  const fileNamePreview = document.getElementById('pdfFileName');
  const auditBtn = document.getElementById('runPdfAuditBtn');

  dropZone.addEventListener('click', () => fileInput.click());

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      fileInput.files = e.dataTransfer.files;
      handleSelectedPdf(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleSelectedPdf(fileInput.files[0]);
    }
  });

  function handleSelectedPdf(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      alert('Please upload a valid PDF document.');
      return;
    }
    fileNamePreview.textContent = `Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
    auditBtn.disabled = false;
  }

  // Setup custom sector toggle
  const sectorSelect = document.getElementById('pdfSectorSelect');
  const customSectorInput = document.getElementById('pdfCustomSectorInput');
  if (sectorSelect && customSectorInput) {
    sectorSelect.addEventListener('change', () => {
      customSectorInput.classList.toggle('hidden', sectorSelect.value !== 'custom');
      if (sectorSelect.value === 'custom') customSectorInput.focus();
    });
  }

  // Setup Apple 2024 fast sample audit
  const appleSampleBtn = document.getElementById('loadAppleSampleBtn');
  if (appleSampleBtn) {
    appleSampleBtn.addEventListener('click', async () => {
      const progressWrapper = document.getElementById('pdfProgressWrapper');
      const progressBar = document.getElementById('pdfProgressBar');
      const progressText = document.getElementById('pdfProgressText');

      progressWrapper.classList.remove('hidden');
      appleSampleBtn.disabled = true;
      progressBar.style.width = '35%';
      progressText.textContent = 'Parsing and cross-referencing Apple 2024 Environmental Progress Report...';

      try {
        const res = await fetch('/api/sample-apple');
        if (!res.ok) throw new Error('Failed to load official Apple sample report');

        progressBar.style.width = '100%';
        progressText.textContent = 'Audit complete. Updating benchmark...';
        const auditedCompany = await res.json();

        await loadBenchmarkData();

        setTimeout(() => {
          progressWrapper.classList.add('hidden');
          appleSampleBtn.disabled = false;
          displayCompanyAudit(auditedCompany, 'Apple 2024 Audit');
          
          const compSelect = document.getElementById('companySelect');
          if (compSelect) compSelect.value = auditedCompany.company;
        }, 300);

      } catch (err) {
        progressWrapper.classList.add('hidden');
        appleSampleBtn.disabled = false;
        alert(`Apple report load error: ${err.message}`);
      }
    });
  }

  auditBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) return;

    const companyName = document.getElementById('pdfCompanyName').value.trim();
    const sectorVal = document.getElementById('pdfSectorSelect') ? document.getElementById('pdfSectorSelect').value : '';
    const sector = (sectorVal === 'custom') 
      ? (document.getElementById('pdfCustomSectorInput').value.trim() || 'Custom') 
      : sectorVal;
    const maxClaims = parseInt(document.getElementById('maxClaimsInput').value, 10) || 10;
    const autoSave = document.getElementById('autoSaveBenchmarkCheckbox') ? document.getElementById('autoSaveBenchmarkCheckbox').checked : true;

    const progressWrapper = document.getElementById('pdfProgressWrapper');
    const progressBar = document.getElementById('pdfProgressBar');
    const progressText = document.getElementById('pdfProgressText');

    progressWrapper.classList.remove('hidden');
    auditBtn.disabled = true;
    progressBar.style.width = '20%';
    progressText.textContent = 'Uploading PDF and parsing text and tables...';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('company_name', companyName);
    formData.append('sector', sector);
    formData.append('max_claims', maxClaims);
    formData.append('auto_save', autoSave ? 'true' : 'false');
    formData.append('provider', state.provider);
    formData.append('api_key', state.apiKey);
    formData.append('model', state.model);

    try {
      progressBar.style.width = '55%';
      progressText.textContent = 'Cross-referencing vector standards and auditing claims...';

      const res = await fetch('/api/audit/pdf', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server error: ${res.status}`);
      }

      progressBar.style.width = '100%';
      progressText.textContent = 'Audit complete. Preparing findings view...';

      const auditedCompany = await res.json();
      
      if (autoSave) {
        await loadBenchmarkData();
      }

      setTimeout(() => {
        progressWrapper.classList.add('hidden');
        auditBtn.disabled = false;
        displayCompanyAudit(auditedCompany, auditedCompany.engine || 'Report Audit');
        
        const compSelect = document.getElementById('companySelect');
        if (compSelect) compSelect.value = auditedCompany.company;
      }, 400);

    } catch (err) {
      progressWrapper.classList.add('hidden');
      auditBtn.disabled = false;
      alert(`Audit failed: ${err.message}`);
      console.error(err);
    }
  });
}

// =============================================================================
// TAB 2: Sector Benchmark
// =============================================================================
function renderBenchmarkTab() {
  if (!state.companies || state.companies.length === 0) return;

  const currentSector = state.selectedSector || 'all';
  const filtered = (currentSector === 'all')
    ? state.companies
    : state.companies.filter(c => (c.sector || '').toLowerCase() === currentSector.toLowerCase());

  const countPill = document.getElementById('sectorCompanyCount');
  if (countPill) {
    countPill.textContent = `${filtered.length} compan${filtered.length === 1 ? 'y' : 'ies'} analyzed ${currentSector !== 'all' ? `(${currentSector})` : ''}`;
  }

  // Adjust radar selected companies if filtered doesn't include them
  const filteredNames = filtered.map(c => c.company);
  state.radarSelectedCompanies = state.radarSelectedCompanies.filter(n => filteredNames.includes(n));
  if (state.radarSelectedCompanies.length === 0 && filteredNames.length > 0) {
    state.radarSelectedCompanies = filteredNames.slice(0, 4);
  }

  renderLeaderboardChart(filtered);
  renderRadarPills(filtered);
  renderRadarChart(filtered);
  renderTalkVsWalkChart(filtered);
  renderBenchmarkTable(filtered);
}

function renderLeaderboardChart(companies) {
  const comps = companies || state.companies;
  const sorted = [...comps].sort((a, b) => a.greenwashing_risk_index - b.greenwashing_risk_index);
  const labels = sorted.map(c => (c.is_custom ? `${c.company} (Custom)` : c.company));
  const data = sorted.map(c => c.greenwashing_risk_index);
  const colors = data.map(val => val <= 48 ? '#10b981' : (val <= 74 ? '#d97706' : '#e11d48'));

  const ctx = document.getElementById('leaderboardChart').getContext('2d');
  if (state.charts.leaderboard) state.charts.leaderboard.destroy();

  state.charts.leaderboard = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'GWRI Risk Score (%)',
        data: data,
        backgroundColor: colors,
        borderRadius: 2,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          grid: { display: false },
          ticks: { color: '#cbd5e1', font: { family: 'Inter', size: 11, weight: '500' } }
        }
      },
      plugins: {
        legend: { display: false }
      }
    }
  });
}

function renderRadarPills(companies) {
  const comps = companies || state.companies;
  const container = document.getElementById('radarCompanyPills');
  container.innerHTML = '';

  comps.forEach(comp => {
    const pill = document.createElement('button');
    const isSelected = state.radarSelectedCompanies.includes(comp.company);
    pill.className = `radar-pill ${isSelected ? 'selected' : ''}`;
    pill.textContent = (comp.is_custom ? '[Custom] ' : '') + comp.company;

    pill.addEventListener('click', () => {
      if (state.radarSelectedCompanies.includes(comp.company)) {
        if (state.radarSelectedCompanies.length > 1) {
          state.radarSelectedCompanies = state.radarSelectedCompanies.filter(c => c !== comp.company);
        }
      } else {
        state.radarSelectedCompanies.push(comp.company);
      }
      renderRadarPills(comps);
      renderRadarChart(comps);
    });

    container.appendChild(pill);
  });
}

function renderRadarChart(companies) {
  const comps = companies || state.companies;
  const radarColors = [
    { border: '#38bdf8', bg: 'rgba(56, 189, 248, 0.12)' },
    { border: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
    { border: '#d97706', bg: 'rgba(217, 119, 6, 0.12)' },
    { border: '#e11d48', bg: 'rgba(225, 29, 72, 0.12)' },
    { border: '#818cf8', bg: 'rgba(129, 140, 248, 0.12)' },
    { border: '#06b6d4', bg: 'rgba(6, 182, 212, 0.12)' },
  ];

  const datasets = state.radarSelectedCompanies.map((name, idx) => {
    const comp = comps.find(c => c.company === name) || state.companies.find(c => c.company === name);
    if (!comp) return null;

    // Calculate mean pillar scores from claims
    const claims = comp.claims || [];
    let q = 50, t = 50, s = 50, a = 50;
    if (claims.length > 0) {
      q = claims.reduce((acc, c) => acc + (c.pillar_scores?.quantification || 50), 0) / claims.length;
      t = claims.reduce((acc, c) => acc + (c.pillar_scores?.trajectory || 50), 0) / claims.length;
      s = claims.reduce((acc, c) => acc + (c.pillar_scores?.scope || 50), 0) / claims.length;
      a = claims.reduce((acc, c) => acc + (c.pillar_scores?.assurance || 50), 0) / claims.length;
    }

    const cScheme = radarColors[idx % radarColors.length];
    return {
      label: comp.company,
      data: [q, t, s, a],
      borderColor: cScheme.border,
      backgroundColor: cScheme.bg,
      borderWidth: 1.5,
      pointRadius: 2.5,
    };
  }).filter(Boolean);

  const ctx = document.getElementById('radarChart').getContext('2d');
  if (state.charts.radar) state.charts.radar.destroy();

  state.charts.radar = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: ['Quantification (30%)', 'Trajectory & Roadmap (25%)', 'Scope & Materiality (25%)', 'Assurance (20%)'],
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          min: 0,
          max: 100,
          ticks: { color: '#64748b', backdropColor: 'transparent', stepSize: 25, font: { family: 'JetBrains Mono', size: 9 } },
          grid: { color: 'rgba(255, 255, 255, 0.07)' },
          angleLines: { color: 'rgba(255, 255, 255, 0.07)' },
          pointLabels: { color: '#94a3b8', font: { family: 'Inter', size: 10, weight: '500' } }
        }
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 }, boxWidth: 10, padding: 12 }
        }
      }
    }
  });
}

function renderTalkVsWalkChart(companies) {
  const comps = companies || state.companies;
  const points = comps.map(c => {
    const x = c.marketing_claim_volume || 50;
    const y = (100 - (c.greenwashing_risk_index || 50)); // Empirical verification = 100 - GWRI
    return {
      x: x,
      y: y,
      company: c.company,
      gwri: c.greenwashing_risk_index,
      is_custom: c.is_custom,
    };
  });

  const ctx = document.getElementById('talkVsWalkChart').getContext('2d');
  if (state.charts.talkVsWalk) state.charts.talkVsWalk.destroy();

  state.charts.talkVsWalk = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [{
        label: 'Companies',
        data: points,
        backgroundColor: points.map(p => p.gwri <= 48 ? '#10b981' : (p.gwri <= 74 ? '#d97706' : '#e11d48')),
        pointRadius: 6,
        pointHoverRadius: 8,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: { display: true, text: 'Marketing Volume Index (Disclosure Volume)', color: '#64748b', font: { size: 11 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          title: { display: true, text: 'Empirical Verification Score (Substantiation)', color: '#64748b', font: { size: 11 } },
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              const p = ctx.raw;
              return `${p.company}: Talk=${p.x}, Walk=${p.y.toFixed(1)}% (Risk: ${p.gwri}%)`;
            }
          }
        }
      }
    }
  });
}

function renderBenchmarkTable(companies) {
  const comps = companies || state.companies;
  const tbody = document.getElementById('benchmarkTableBody');
  tbody.innerHTML = '';

  comps.forEach(c => {
    const gwri = c.greenwashing_risk_index || 0;
    const legitRatio = (c.legit_claim_ratio || 0) * 100;
    const riskBadge = gwri <= 48 
      ? '<span class="badge-legit">Verified</span>' 
      : (gwri <= 74 ? '<span class="badge-grey">Incomplete</span>' : '<span class="badge-bullshit">High Risk</span>');

    const customTag = c.is_custom ? '<span class="badge-tag" style="font-size:0.65rem;margin-left:4px;">Custom</span>' : '';
    const deleteBtn = c.is_custom 
      ? `<button class="btn btn-xs btn-outline delete-btn" data-company="${c.company}" title="Delete from benchmark" style="padding:4px 7px;color:#f43f5e;border-color:rgba(244,63,94,0.3);"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>` 
      : '';
    const viewBtn = `<button class="btn btn-xs btn-outline view-btn" data-company="${c.company}" style="padding:4px 9px;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>View</button>`;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><b>${c.company}</b> ${customTag}</td>
      <td><span class="sector-badge" style="font-size:0.7rem;">${c.sector || 'Other'}</span></td>
      <td><code>${c.ticker || 'N/A'}</code></td>
      <td>${riskBadge} <span class="mono-num">${gwri.toFixed(1)}%</span></td>
      <td><span class="mono-num">${legitRatio.toFixed(0)}%</span></td>
      <td><span class="mono-num">${c.scope3_completeness || 0}%</span></td>
      <td>${c.assurance_level || 'None'}</td>
      <td style="display:flex;gap:6px;align-items:center;">
        ${viewBtn}
        ${deleteBtn}
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Attach event handlers
  tbody.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.getAttribute('data-company');
      const comp = state.companies.find(c => c.company === name);
      if (comp) {
        displayCompanyAudit(comp, comp.is_custom ? 'Custom Audited Report' : 'Benchmark Dataset');
        const compSelect = document.getElementById('companySelect');
        if (compSelect) compSelect.value = comp.company;
        switchTab('tab-screener');
      }
    });
  });

  tbody.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.getAttribute('data-company');
      if (confirm(`Do you want to delete company "${name}" from the sector benchmark?`)) {
        try {
          const res = await fetch(`/api/benchmark/companies/${encodeURIComponent(name)}`, { method: 'DELETE' });
          if (!res.ok) throw new Error('Failed to delete company from benchmark');
          await loadBenchmarkData();
        } catch (err) {
          alert(err.message);
        }
      }
    });
  });
}

// =============================================================================
// TAB 3: Live RAG Claim Tester
// =============================================================================
function setupClaimTester() {
  const select = document.getElementById('sampleClaimsSelect');
  const textarea = document.getElementById('customClaimText');
  const btn = document.getElementById('auditClaimBtn');

  select.addEventListener('change', () => {
    if (select.value) {
      textarea.value = select.value;
    }
  });

  btn.addEventListener('click', async () => {
    const text = textarea.value.trim();
    if (!text) {
      alert('Please enter or select an environmental statement to verify.');
      return;
    }

    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> <span>Verifying Claim Against Standards...</span>`;

    try {
      const res = await fetch('/api/audit/claim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          provider: state.provider,
          api_key: state.apiKey,
          model: state.model,
        })
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      displayClaimAuditResult(data, text);
    } catch (err) {
      alert(`Claim verification failed: ${err.message}`);
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <span>Verify Disclosure Against Standards</span>
      `;
    }
  });
}

function displayClaimAuditResult(auditResult, rawText) {
  const box = document.getElementById('claimTestResultBox');
  box.classList.remove('hidden');

  const claim = auditResult.claim || {};
  const cls = claim.classification || 'grey';
  const risk = claim.risk_score || 50;
  const pScores = claim.pillar_scores || {};
  const pRats = claim.pillar_rationales || {};

  // Badge & score
  const badgeEl = document.getElementById('testResultBadge');
  badgeEl.className = `badge-${cls}`;
  badgeEl.textContent = cls === 'legit' ? 'VERIFIED' : (cls === 'grey' ? 'INCOMPLETE' : 'HIGH RISK');
  document.getElementById('testResultScore').textContent = `Risk ${risk.toFixed(0)}%`;

  // Matched standard
  document.getElementById('testResultMatchedStd').textContent = `Standard: ${claim.matched_standard || 'ESG Standard'}`;

  // Quote & Verdict
  document.getElementById('testResultQuote').textContent = `"${rawText}"`;
  document.getElementById('testResultVerdict').innerHTML = `<b>Audit Finding &amp; Assessment:</b> ${claim.audit_justification || 'Analyzed against regulatory criteria.'}`;

  // 4 Pillars
  document.getElementById('testPillarQuant').textContent = `${(pScores.quantification || 50).toFixed(0)}%`;
  document.getElementById('testPillarQuantDesc').textContent = pRats.quantification || 'Physical metrics';

  document.getElementById('testPillarRoadmap').textContent = `${(pScores.trajectory || 50).toFixed(0)}%`;
  document.getElementById('testPillarRoadmapDesc').textContent = pRats.trajectory || 'Baselines & interim targets';

  document.getElementById('testPillarScope').textContent = `${(pScores.scope || 50).toFixed(0)}%`;
  document.getElementById('testPillarScopeDesc').textContent = pRats.scope || 'Scopes covered';

  document.getElementById('testPillarAssur').textContent = `${(pScores.assurance || 50).toFixed(0)}%`;
  document.getElementById('testPillarAssurDesc').textContent = pRats.assurance || 'Audit assurance';

  // Retrieved passages
  const passagesList = document.getElementById('retrievedPassagesList');
  passagesList.innerHTML = '';
  const retrieved = auditResult.retrieved || [];
  if (retrieved.length === 0) {
    passagesList.innerHTML = `<div class="text-muted text-xs">No vector passages retrieved.</div>`;
  } else {
    retrieved.forEach(r => {
      const p = document.createElement('div');
      p.className = 'passage-item';
      p.innerHTML = `
        <div class="passage-title">
          <span>[${r.chunk.tag}] ${r.chunk.title}</span>
          <span style="font-family: var(--font-mono); color: #34d399;">Sim: ${r.score.toFixed(3)}</span>
        </div>
        <div class="passage-body">${r.chunk.body}</div>
      `;
      passagesList.appendChild(p);
    });
  }

  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// =============================================================================
// TAB 4: Standards & Taxonomy
// =============================================================================
function renderStandardsCorpus(standards) {
  document.getElementById('standardsCount').textContent = standards.length;
  const grid = document.getElementById('standardsGridContainer');
  grid.innerHTML = '';

  standards.forEach(std => {
    const card = document.createElement('div');
    card.className = 'standard-card';
    card.setAttribute('data-tag', (std.tag || '').toLowerCase());
    card.setAttribute('data-title', (std.title || '').toLowerCase());
    card.setAttribute('data-preview', (std.preview || '').toLowerCase());

    card.innerHTML = `
      <div class="standard-tag">[${std.tag || 'STD'}] ${std.standard || ''}</div>
      <div class="standard-title">${std.title || 'Standard'}</div>
      <div class="standard-preview">${std.preview || ''}...</div>
    `;
    grid.appendChild(card);
  });
}

function setupStandardsSearch() {
  const input = document.getElementById('standardsSearchInput');
  input.addEventListener('input', () => {
    const query = input.value.trim().toLowerCase();
    const cards = document.querySelectorAll('.standard-card');
    cards.forEach(card => {
      const tag = card.getAttribute('data-tag');
      const title = card.getAttribute('data-title');
      const prev = card.getAttribute('data-preview');
      const match = !query || tag.includes(query) || title.includes(query) || prev.includes(query);
      card.style.display = match ? 'flex' : 'none';
    });
  });
}

// =============================================================================
// Settings Modal
// =============================================================================
function setupSettingsModal() {
  const modal = document.getElementById('settingsModal');
  const openBtn = document.getElementById('openSettingsBtn');
  const closeBtn = document.getElementById('closeSettingsBtn');
  const cancelBtn = document.getElementById('cancelSettingsBtn');
  const saveBtn = document.getElementById('saveSettingsBtn');

  const providerSelect = document.getElementById('providerSelect');
  const apiKeyInput = document.getElementById('apiKeyInput');
  const modelInput = document.getElementById('modelInput');
  const activeLabel = document.getElementById('activeProviderLabel');

  // Load initial settings
  providerSelect.value = state.provider;
  apiKeyInput.value = state.apiKey;
  modelInput.value = state.model;
  activeLabel.textContent = state.provider.replace(' Fallback', '');

  openBtn.addEventListener('click', () => {
    modal.classList.remove('hidden');
  });

  const closeModal = () => modal.classList.add('hidden');
  closeBtn.addEventListener('click', closeModal);
  cancelBtn.addEventListener('click', closeModal);

  saveBtn.addEventListener('click', () => {
    state.provider = providerSelect.value;
    state.apiKey = apiKeyInput.value.trim();
    state.model = modelInput.value.trim();

    localStorage.setItem('gw_provider', state.provider);
    localStorage.setItem('gw_api_key', state.apiKey);
    localStorage.setItem('gw_model', state.model);

    activeLabel.textContent = state.provider.replace(' Fallback', '');
    closeModal();
  });
}
