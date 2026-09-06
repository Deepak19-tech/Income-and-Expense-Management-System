document.addEventListener('DOMContentLoaded', () => {
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const isDarkTheme = () => document.documentElement.dataset.theme === 'dark';
  const syncThemeToggle = () => {
    if (!themeToggle) return;
    themeToggle.innerHTML = isDarkTheme()
      ? '<i class="bi bi-sun"></i><span class="d-lg-none ms-2">Light mode</span>'
      : '<i class="bi bi-moon-stars"></i><span class="d-lg-none ms-2">Dark mode</span>';
    themeToggle.setAttribute('aria-label', isDarkTheme() ? 'Switch to light mode' : 'Switch to dark mode');
  };
  syncThemeToggle();
  themeToggle?.addEventListener('click', () => {
    localStorage.setItem('hisabkitab-theme-v2', isDarkTheme() ? 'light' : 'dark');
    window.location.reload();
  });

  const alerts = document.querySelectorAll('.alert');
  alerts.forEach((alert) => window.setTimeout(() => alert.classList.add('fade'), 4500));

  const typeSelect = document.getElementById('quick_tx_type');
  const categorySelect = document.getElementById('quick_category');
  if (typeSelect && categorySelect) {
    const expenseFields = document.querySelectorAll('.expense-field');
    const updateTransactionFields = () => {
      const type = typeSelect.value;
      [...categorySelect.options].forEach((option) => { option.hidden = option.dataset.type !== type; });
      const firstMatchingCategory = [...categorySelect.options].find((option) => !option.hidden);
      if (firstMatchingCategory) categorySelect.value = firstMatchingCategory.value;
      expenseFields.forEach((field) => field.classList.toggle('d-none', type !== 'expense'));
    };
    typeSelect.addEventListener('change', updateTransactionFields);
    updateTransactionFields();
  }

  const readChartData = (id) => JSON.parse(document.getElementById(id)?.textContent || '[]');
  const trendCanvas = document.getElementById('trendChart');
  if (trendCanvas && window.Chart) {
    const chartText = isDarkTheme() ? '#aebbd0' : '#758198';
    const chartGrid = isDarkTheme() ? 'rgba(169,188,218,.14)' : '#edf1f6';
    const chartContext = trendCanvas.getContext('2d');
    const incomeGradient = chartContext.createLinearGradient(0, 0, 0, 340);
    incomeGradient.addColorStop(0, 'rgba(22,134,91,.25)'); incomeGradient.addColorStop(1, 'rgba(22,134,91,0)');
    const expenseGradient = chartContext.createLinearGradient(0, 0, 0, 340);
    expenseGradient.addColorStop(0, 'rgba(211,77,99,.20)'); expenseGradient.addColorStop(1, 'rgba(211,77,99,0)');
    new Chart(trendCanvas, { type: 'line', data: { labels: readChartData('chart-months'), datasets: [
      { label: 'Income', data: [...readChartData('chart-income'), ...Array(3).fill(null)], borderColor: '#45e0a0', backgroundColor: incomeGradient, fill: true, tension: .4, borderWidth: 3, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: '#45e0a0', pointBorderWidth: 2 },
      { label: 'Expenses', data: [...readChartData('chart-expense'), ...Array(3).fill(null)], borderColor: '#ff7185', backgroundColor: expenseGradient, fill: true, tension: .4, borderWidth: 3, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: '#ff7185', pointBorderWidth: 2 },
      { label: 'Projected income', data: readChartData('chart-forecast-income'), borderColor: '#45e0a0', borderDash: [6, 6], fill: false, tension: .4, borderWidth: 2, pointRadius: 0 },
      { label: 'Projected expenses', data: readChartData('chart-forecast-expense'), borderColor: '#ff7185', borderDash: [6, 6], fill: false, tension: .4, borderWidth: 2, pointRadius: 0 }
    ] }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { labels: { color: chartText, usePointStyle: true, boxWidth: 8, font: { family: 'DM Sans', weight: '600' } } } }, scales: { x: { grid: { display: false }, ticks: { color: chartText, maxRotation: 0 } }, y: { beginAtZero: true, grid: { color: chartGrid }, ticks: { color: chartText } } } } });
  }
  const pieCanvas = document.getElementById('pieChart');
  if (pieCanvas && window.Chart) {
    new Chart(pieCanvas, { type: 'doughnut', data: { labels: readChartData('chart-category-labels'), datasets: [{ data: readChartData('chart-category-values'), backgroundColor: ['#1455c9','#35a7e9','#16865b','#ffbd38','#d34d63','#8c6de9'], borderWidth: 0, hoverOffset: 5 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '68%', plugins: { legend: { position: 'bottom', labels: { color: isDarkTheme() ? '#c9d5e7' : '#4e5c72', usePointStyle: true, boxWidth: 8, padding: 16, font: { family: 'DM Sans', weight: '600' } } } } } });
  }

  const tourSteps = [
    { target: '[data-tour="overview"]', title: 'Your financial command center', copy: 'A clear snapshot of your balance, income, expenses, and savings for the month.' },
    { target: '[data-tour="balance"]', title: 'See the signal at a glance', copy: 'These metric cards keep the important movement in your money visible without digging.' },
    { target: '[data-tour="forecast"]', title: 'Look 90 days ahead', copy: 'The outlook blends your recent cash flow with a projection so you can plan before the month arrives.' },
    { target: '[data-tour="ledger"]', title: 'Move from insight to action', copy: 'Review your latest transactions or use Add transaction whenever you need to capture a new one.' }
  ];
  const tourCard = document.querySelector('[data-tour-card]');
  const tourOverlay = document.querySelector('[data-tour-overlay]');
  const tourNext = document.querySelector('[data-tour-next]');
  if (tourCard && tourOverlay && !localStorage.getItem('hisabkitab-tour-complete')) {
    let tourIndex = 0;
    const finishTour = () => { localStorage.setItem('hisabkitab-tour-complete', '1'); tourCard.hidden = true; tourOverlay.hidden = true; document.querySelectorAll('.tour-focus').forEach((node) => node.classList.remove('tour-focus')); };
    const renderTour = () => {
      const step = tourSteps[tourIndex];
      const target = document.querySelector(step.target);
      if (!target) return finishTour();
      document.querySelectorAll('.tour-focus').forEach((node) => node.classList.remove('tour-focus'));
      target.classList.add('tour-focus');
      tourCard.querySelector('[data-tour-title]').textContent = step.title;
      tourCard.querySelector('[data-tour-copy]').textContent = step.copy;
      tourCard.querySelector('[data-tour-step]').textContent = `0${tourIndex + 1} / 04`;
      tourCard.querySelector('[data-tour-dots]').innerHTML = tourSteps.map((_, index) => `<i class="${index === tourIndex ? 'active' : ''}"></i>`).join('');
      tourNext.innerHTML = tourIndex === tourSteps.length - 1 ? 'Finish <i class="bi bi-check2"></i>' : 'Show me around <i class="bi bi-arrow-right"></i>';
      const rect = target.getBoundingClientRect();
      tourCard.style.top = `${Math.min(window.innerHeight - 230, rect.bottom + 18)}px`;
      tourCard.style.left = `${Math.min(window.innerWidth - 360, Math.max(18, rect.left))}px`;
    };
    tourCard.hidden = false; tourOverlay.hidden = false; renderTour();
    tourNext.addEventListener('click', () => { tourIndex += 1; if (tourIndex >= tourSteps.length) finishTour(); else renderTour(); });
    tourCard.querySelector('[data-tour-skip]').addEventListener('click', finishTour);
    window.addEventListener('resize', renderTour);
  }
});
