/**
 * CoastCapital Platform Navigation
 * Shared cross-module navigation bar injected into every module.
 *
 * Usage: Add to any page:
 *   <link rel="stylesheet" href="/static/brand/css/nav.css">
 *   <script src="/static/brand/js/nav.js" defer></script>
 *   <body data-cc-module="finance" data-cc-page="dashboard">
 */
(function () {
  'use strict';

  /* ── Navigation tree ───────────────────────────────────────────── */
  const MODULES = [
    {
      id: 'finance',
      label: 'Finance',
      port: 5000,
      pages: [
        { id: 'dashboard', label: 'Market Dashboard', path: '/dashboard' }
      ]
    },
    {
      id: 'sports',
      label: 'Sports',
      port: 5300,
      pages: [
        { id: 'dashboard',           label: 'Sports Summary',      path: '/dashboard' },
        { id: 'betting',             label: 'Betting',             path: '/dashboard/betting' },
        { id: 'model_performance',   label: 'Model Performance',   path: '/dashboard/model-performance' },
        { id: 'model_diagnostics',   label: 'Model Diagnostics',   path: '/dashboard/model-diagnostics' }
      ]
    },
    {
      id: 'homelab',
      label: 'HomeLab',
      port: 5200,
      pages: [
        { id: 'dashboard', label: 'Infrastructure', path: '/dashboard' }
      ]
    },
    {
      id: 'assistant',
      label: 'Assistant',
      port: 5100,
      pages: [
        { id: 'dashboard',     label: 'Dashboard',     path: '/dashboard' },
        { id: 'action-plan',   label: 'Action Plan',   path: '/communications' },
        { id: 'relationships', label: 'Relationships',  path: '/relationships' }
      ]
    },
    {
      id: 'database',
      label: 'Database',
      port: 8081,
      pages: [
        { id: 'dashboard', label: 'Health Dashboard', path: '/dashboard' }
      ]
    },
    {
      id: 'platform',
      label: 'Platform',
      port: 5400,
      pages: [
        { id: 'dispatcher', label: 'Dispatcher Feedback', path: '/dashboard' }
      ]
    },
    {
      id: 'n8n',
      label: 'N8N',
      port: 5678,
      pages: [
        { id: 'dashboard', label: 'Workflows', path: '/' }
      ]
    }
  ];

  /* ── Detect current context ────────────────────────────────────── */
  const host = window.location.hostname;
  const currentModule = document.body.dataset.ccModule || '';
  const currentPage   = document.body.dataset.ccPage   || '';

  function moduleUrl(mod, path) {
    return 'http://' + host + ':' + mod.port + path;
  }

  /* ── Build nav HTML ────────────────────────────────────────────── */
  function buildNav() {
    var header = document.createElement('header');
    header.id = 'cc-platform-nav';

    var inner = document.createElement('div');
    inner.className = 'ccn-inner';

    // Logo
    var logo = document.createElement('a');
    logo.className = 'ccn-logo';
    logo.href = moduleUrl(MODULES[0], '/dashboard');
    logo.innerHTML =
      '<img src="/static/brand/img/logo-icon.svg" alt="" width="22" height="22">' +
      '<span class="ccn-logo-text">CoastCapital</span>';
    inner.appendChild(logo);

    // Module links
    var nav = document.createElement('nav');
    nav.className = 'ccn-modules';

    MODULES.forEach(function (mod) {
      var isActive = mod.id === currentModule;
      var hasDropdown = mod.pages.length > 1;

      var item = document.createElement('div');
      item.className = 'ccn-module' + (isActive ? ' ccn-active' : '');

      // Top-level link
      var link = document.createElement('a');
      link.className = 'ccn-module-link';
      link.href = moduleUrl(mod, mod.pages[0].path);
      link.textContent = mod.label;

      if (hasDropdown) {
        var caret = document.createElement('span');
        caret.className = 'ccn-caret';
        caret.innerHTML = '&#9662;';
        link.appendChild(caret);
      }

      item.appendChild(link);

      // Dropdown
      if (hasDropdown) {
        var dropdown = document.createElement('div');
        dropdown.className = 'ccn-dropdown';

        mod.pages.forEach(function (page) {
          var a = document.createElement('a');
          a.className = 'ccn-dropdown-item' +
            (isActive && page.id === currentPage ? ' ccn-page-active' : '');
          a.href = moduleUrl(mod, page.path);
          a.textContent = page.label;
          dropdown.appendChild(a);
        });

        item.appendChild(dropdown);

        // Toggle dropdown on click for mobile
        link.addEventListener('click', function (e) {
          if (window.innerWidth <= 768) {
            e.preventDefault();
            item.classList.toggle('ccn-open');
            // Close others
            var siblings = nav.querySelectorAll('.ccn-module.ccn-open');
            for (var i = 0; i < siblings.length; i++) {
              if (siblings[i] !== item) siblings[i].classList.remove('ccn-open');
            }
          }
        });
      }

      nav.appendChild(item);
    });

    inner.appendChild(nav);

    // Hamburger for mobile
    var burger = document.createElement('button');
    burger.className = 'ccn-burger';
    burger.setAttribute('aria-label', 'Toggle navigation');
    burger.innerHTML = '<span></span><span></span><span></span>';
    burger.addEventListener('click', function () {
      header.classList.toggle('ccn-mobile-open');
    });
    inner.appendChild(burger);

    header.appendChild(inner);
    return header;
  }

  /* ── Inject into page ──────────────────────────────────────────── */
  var nav = buildNav();
  document.body.insertBefore(nav, document.body.firstChild);
  document.body.classList.add('ccn-has-nav');
})();
