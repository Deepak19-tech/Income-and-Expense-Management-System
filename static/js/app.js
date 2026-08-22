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
    localStorage.setItem('hisabkitab-theme', isDarkTheme() ? 'light' : 'dark');
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
      { label: 'Income', data: readChartData('chart-income'), borderColor: '#16865b', backgroundColor: incomeGradient, fill: true, tension: .4, borderWidth: 3, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: '#fff', pointBorderWidth: 2 },
      { label: 'Expenses', data: readChartData('chart-expense'), borderColor: '#d34d63', backgroundColor: expenseGradient, fill: true, tension: .4, borderWidth: 3, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: '#fff', pointBorderWidth: 2 }
    ] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: chartText, usePointStyle: true, boxWidth: 8, font: { family: 'DM Sans', weight: '600' } } } }, scales: { x: { grid: { display: false }, ticks: { color: chartText } }, y: { beginAtZero: true, grid: { color: chartGrid }, ticks: { color: chartText } } } } });
  }
  const pieCanvas = document.getElementById('pieChart');
  if (pieCanvas && window.Chart) {
    new Chart(pieCanvas, { type: 'doughnut', data: { labels: readChartData('chart-category-labels'), datasets: [{ data: readChartData('chart-category-values'), backgroundColor: ['#1455c9','#35a7e9','#16865b','#ffbd38','#d34d63','#8c6de9'], borderWidth: 0, hoverOffset: 5 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '68%', plugins: { legend: { position: 'bottom', labels: { color: isDarkTheme() ? '#c9d5e7' : '#4e5c72', usePointStyle: true, boxWidth: 8, padding: 16, font: { family: 'DM Sans', weight: '600' } } } } } });
  }
});
