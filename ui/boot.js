/**
 * Browser plugin shell.boot — header dropdown (list / + New browser / Settings).
 * No "default shell" row. Multi-tab via browser_pane_new_window + data-tab-id.
 */
(function () {
  "use strict";

  var PLUGIN_ID = "browser";
  var PANEL_ID = "browser";
  var TAB_PREFIX = "plugin:browser:browser";
  var HOMEPAGE_DEFAULT = "https://uefnducky.org";
  var HOMEPAGE_LEGACY = "https://duckduckgo.com";
  var HISTORY_MAX = 200;
  var MENU_WIDTH = 280;
  var MENU_GAP = 6;

  var host = window.__duckyPluginHost && window.__duckyPluginHost.forPlugin
    ? window.__duckyPluginHost.forPlugin(PLUGIN_ID)
    : null;

  var paneState = {};
  var menuEl = null;
  var settingsEl = null;
  var triggerBtn = null;
  var badgeEl = null;
  var open = false;
  var mo = null;
  var pollTimer = null;
  var searchChoice = null;
  var searchEngineValue = "duckduckgo";

  var SEARCH_OPTIONS = [
    { value: "duckduckgo", label: "DuckDuckGo" },
    { value: "google", label: "Google" },
    { value: "bing", label: "Bing" },
    { value: "custom", label: "Custom URL template" },
  ];

  function prefs() {
    return (host && host.prefs && host.prefs.get()) || {};
  }

  function setPrefs(patch) {
    if (host && host.prefs) host.prefs.set(patch);
  }

  function homepage() {
    var v = prefs().homepage;
    if (typeof v !== "string" || !v.trim()) return HOMEPAGE_DEFAULT;
    var t = v.trim().replace(/\/+$/, "");
    if (t === HOMEPAGE_LEGACY || t === "http://duckduckgo.com") {
      setPrefs({ homepage: HOMEPAGE_DEFAULT });
      return HOMEPAGE_DEFAULT;
    }
    return t || HOMEPAGE_DEFAULT;
  }

  function api() {
    var a = window.pywebview && window.pywebview.api;
    return a && typeof a.browser_pane_list === "function" ? a : null;
  }

  function isBrowserHeaderBtn(el) {
    if (!el || !el.closest) return null;
    var btn = el.closest(".plugin-header-btn");
    if (!btn) return null;
    var label = (btn.getAttribute("aria-label") || btn.getAttribute("title") || "").toLowerCase();
    if (label.indexOf("browser") >= 0 || label.indexOf("web browser") >= 0) return btn;
    return null;
  }

  function findTrigger() {
    var buttons = document.querySelectorAll(".plugin-header-btn");
    for (var i = 0; i < buttons.length; i++) {
      if (isBrowserHeaderBtn(buttons[i])) return buttons[i];
    }
    return null;
  }

  function listTabIds() {
    var nodes = document.querySelectorAll('[data-tab-id^="' + TAB_PREFIX + '"]');
    var ids = [];
    for (var i = 0; i < nodes.length; i++) {
      var id = nodes[i].getAttribute("data-tab-id");
      if (id && ids.indexOf(id) < 0) ids.push(id);
    }
    return ids;
  }

  function activeTabId() {
    var el = document.querySelector('.editor-tab.is-active[data-tab-id^="' + TAB_PREFIX + '"]');
    return el ? el.getAttribute("data-tab-id") : "";
  }

  function activateTab(tabId) {
    var el = document.querySelector('[data-tab-id="' + cssEscape(tabId) + '"]');
    if (el) el.click();
  }

  function closeTab(tabId) {
    var el = document.querySelector('[data-tab-id="' + cssEscape(tabId) + '"]');
    if (!el) return;
    var btn = el.querySelector(".editor-tab-close-btn");
    if (btn) btn.click();
  }

  function cssEscape(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/["\\]/g, "\\$&");
  }

  function newBrowser() {
    var url = homepage();
    // Close the dropdown first — never stack menu DOM work on a WebView2 boot.
    hideMenu();
    var ids = listTabIds();
    // First browser: open the singleton panel tab (same as header `panel:browser`).
    // Do NOT use browser_pane_new_window here — that path was freezing on cold start.
    if (!ids.length) {
      if (typeof window.__duckyOpenPluginUiTab === "function") {
        window.__duckyOpenPluginUiTab(PLUGIN_ID, PANEL_ID);
        return;
      }
      // Pre-helper hosts: temporarily unhook our capture click and fire the button.
      var btn = findTrigger();
      if (btn) {
        btn.removeEventListener("click", onTriggerClick, true);
        btn.click();
        btn.addEventListener("click", onTriggerClick, true);
      }
      return;
    }
    // Additional browsers: new instance tab + shared WebView2 env (host serializes).
    if (typeof window.__uefnPanelPush === "function") {
      window.__uefnPanelPush({
        type: "browser_pane_new_window",
        pane_id: TAB_PREFIX,
        url: url,
      });
    }
  }

  function pushHistory(url, title) {
    if (!url || url === "about:blank") return;
    if (/^https?:\/\/(127\.0\.0\.1|localhost|::1)(:|\/|$)/i.test(url)) return;
    if (url.indexOf("/plugin-ui/") >= 0) return;
    var list = Array.isArray(prefs().history) ? prefs().history.slice() : [];
    list = list.filter(function (h) {
      return h && h.url !== url;
    });
    list.unshift({ url: url, title: title || url, at: Date.now() });
    if (list.length > HISTORY_MAX) list = list.slice(0, HISTORY_MAX);
    setPrefs({ history: list, lastUrl: url });
  }

  function wrapPanelPush() {
    var prev = window.__uefnPanelPush;
    if (prev && prev.__browserBootWrapped) return;
    function fan(ev) {
      if (ev && ev.type === "browser_pane_state" && ev.pane_id) {
        paneState[ev.pane_id] = ev;
        if (ev.url) pushHistory(ev.url, ev.title || "");
        refreshBadge();
        if (open) renderMenuBody();
      }
      if (typeof prev === "function") prev(ev);
    }
    fan.__browserBootWrapped = true;
    window.__uefnPanelPush = fan;
  }

  function refreshBadge() {
    var btn = findTrigger();
    if (!btn) return;
    triggerBtn = btn;
    var n = listTabIds().length;
    if (!badgeEl) {
      badgeEl = document.createElement("span");
      badgeEl.className = "terminal-header-badge browser-header-badge";
    }
    if (n > 0) {
      badgeEl.textContent = String(n);
      if (!badgeEl.parentNode) {
        btn.style.position = "relative";
        btn.appendChild(badgeEl);
      }
      btn.classList.add("has-terminals");
    } else if (badgeEl.parentNode) {
      badgeEl.parentNode.removeChild(badgeEl);
      btn.classList.remove("has-terminals");
    }
  }

  function hideMenu() {
    open = false;
    if (menuEl && menuEl.parentNode) menuEl.parentNode.removeChild(menuEl);
    menuEl = null;
    if (triggerBtn) triggerBtn.classList.remove("is-active");
  }

  function menuPosition(trigger) {
    var rect = trigger.getBoundingClientRect();
    var left = rect.right - MENU_WIDTH;
    if (left < 8) left = 8;
    if (left + MENU_WIDTH > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - MENU_WIDTH - 8);
    }
    return { top: rect.bottom + MENU_GAP, left: left };
  }

  function renderMenuBody() {
    if (!menuEl) return;
    var list = menuEl.querySelector(".browser-header-list");
    if (!list) return;
    var ids = listTabIds();
    var active = activeTabId();
    list.innerHTML = "";
    if (!ids.length) {
      var empty = document.createElement("p");
      empty.className = "terminal-header-empty";
      empty.textContent = "No browsers";
      list.appendChild(empty);
      return;
    }
    ids.forEach(function (id) {
      var st = paneState[id] || {};
      var row = document.createElement("div");
      row.className = "terminal-header-item" + (id === active ? " is-active" : "");
      var main = document.createElement("button");
      main.type = "button";
      main.className = "terminal-header-item-main";
      var name = document.createElement("span");
      name.className = "terminal-header-item-name";
      name.textContent = st.title || st.url || "Browser";
      var meta = document.createElement("span");
      meta.className = "terminal-header-item-meta";
      var urlHint = document.createElement("span");
      urlHint.className = "terminal-header-item-shell";
      urlHint.textContent = shortenUrl(st.url || "");
      meta.appendChild(urlHint);
      main.appendChild(name);
      main.appendChild(meta);
      main.addEventListener("click", function () {
        activateTab(id);
        hideMenu();
      });
      var close = document.createElement("button");
      close.type = "button";
      close.className = "terminal-header-item-close icon-btn no-drag";
      close.title = "Close browser";
      close.setAttribute("aria-label", "Close browser");
      close.innerHTML =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>';
      close.addEventListener("click", function (e) {
        e.stopPropagation();
        closeTab(id);
        hideMenu();
        setTimeout(refreshBadge, 80);
      });
      row.appendChild(main);
      row.appendChild(close);
      list.appendChild(row);
    });
  }

  function shortenUrl(u) {
    if (!u) return "";
    try {
      var x = new URL(u);
      return x.hostname.replace(/^www\./, "");
    } catch (_) {
      return u.slice(0, 24);
    }
  }

  function showMenu(trigger) {
    hideMenu();
    wrapPanelPush();
    open = true;
    triggerBtn = trigger;
    trigger.classList.add("is-active");
    var pos = menuPosition(trigger);
    menuEl = document.createElement("div");
    menuEl.className = "terminal-header-menu terminal-header-menu--portaled no-drag browser-header-menu";
    menuEl.style.top = pos.top + "px";
    menuEl.style.left = pos.left + "px";
    menuEl.innerHTML =
      '<div class="browser-header-list terminal-header-list"></div>' +
      '<button type="button" class="terminal-header-new-btn browser-header-settings-btn">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
      '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>' +
      "</svg><span>Settings</span></button>" +
      '<button type="button" class="terminal-header-new-btn browser-header-new-btn">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
      '<path d="M12 5v14M5 12h14"/></svg><span>New browser</span></button>';
    document.body.appendChild(menuEl);
    renderMenuBody();
    menuEl.querySelector(".browser-header-settings-btn").addEventListener("click", function () {
      hideMenu();
      openSettings();
    });
    menuEl.querySelector(".browser-header-new-btn").addEventListener("click", function () {
      newBrowser();
      setTimeout(refreshBadge, 200);
    });
    // Enrich labels from live panes when API exists.
    var a = api();
    if (a) {
      Promise.resolve(a.browser_pane_list())
        .then(function (res) {
          var panes = (res && res.panes) || [];
          panes.forEach(function (p) {
            if (p && p.pane_id) paneState[p.pane_id] = p;
          });
          if (open) renderMenuBody();
        })
        .catch(function () {});
    }
  }

  function onTriggerClick(e) {
    var btn = isBrowserHeaderBtn(e.target);
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    if (open) hideMenu();
    else showMenu(btn);
  }

  function onDocDown(e) {
    if (!open) return;
    if (menuEl && menuEl.contains(e.target)) return;
    if (triggerBtn && triggerBtn.contains(e.target)) return;
    hideMenu();
  }

  function onKey(e) {
    if (e.key !== "Escape") return;
    if (settingsEl || document.querySelector(".browser-settings-overlay")) {
      forceCloseSettings();
      return;
    }
    hideMenu();
  }

  /* ── Settings popup ───────────────────────────────────────────────── */

  function setBrowserCover(on) {
    if (typeof window.__duckySetBrowserUiCover === "function") {
      window.__duckySetBrowserUiCover(!!on);
      return;
    }
    // Fallback (pre-cover host): hide panes only; tab RAF restores when cover lifts.
    if (!on) return;
    var a = api();
    if (!a || typeof a.browser_pane_list !== "function") return;
    Promise.resolve(a.browser_pane_list())
      .then(function (res) {
        (res && res.panes ? res.panes : []).forEach(function (p) {
          if (!p || !p.pane_id || typeof a.browser_pane_set_bounds !== "function") return;
          a.browser_pane_set_bounds(p.pane_id, 0, 0, 0, 0, 0, 0, false);
        });
      })
      .catch(function () {});
  }

  function openSettings() {
    if (settingsEl) closeSettings();
    hideMenu();
    setBrowserCover(true);
    try {
      _openSettingsBody();
    } catch (err) {
      console.warn("[browser] settings open failed", err);
      forceCloseSettings();
    }
  }

  function _openSettingsBody() {
    var p = prefs();
    var history = Array.isArray(p.history) ? p.history : [];
    settingsEl = document.createElement("div");
    settingsEl.className = "browser-settings-overlay no-drag";
    settingsEl.innerHTML =
      '<div class="browser-settings-modal" role="dialog" aria-label="Browser settings">' +
      '<header class="browser-settings-head">' +
      "<h2>Browser settings</h2>" +
      '<button type="button" class="icon-btn browser-settings-close" aria-label="Close">×</button>' +
      "</header>" +
      '<div class="browser-settings-body">' +
      '<section class="browser-settings-section">' +
      "<h3>General</h3>" +
      '<label class="browser-settings-field"><span>Homepage</span>' +
      '<input type="text" id="bs-home" spellcheck="false" /></label>' +
      '<div class="browser-settings-field"><span>Search engine</span>' +
      '<div id="bs-search" class="browser-settings-choice"></div></div>' +
      '<label class="browser-settings-field browser-settings-custom" style="display:none"><span>Search URL (use %s)</span>' +
      '<input type="text" id="bs-search-custom" spellcheck="false" placeholder="https://example.com/search?q=%s" /></label>' +
      "</section>" +
      '<section class="browser-settings-section">' +
      "<h3>History</h3>" +
      '<div class="browser-settings-history" id="bs-history"></div>' +
      '<div class="browser-settings-actions">' +
      '<button type="button" class="browser-settings-btn" id="bs-clear-history">Clear history</button>' +
      "</div></section>" +
      '<section class="browser-settings-section">' +
      "<h3>Privacy &amp; data</h3>" +
      '<p class="browser-settings-hint">Clears the in-app Chromium profile (WebView2). Prefer Clear while a Browser tab is open; never force-delete while the profile is locked.</p>' +
      '<div class="browser-settings-actions">' +
      '<button type="button" class="browser-settings-btn" id="bs-clear-cache">Clear cache</button>' +
      '<button type="button" class="browser-settings-btn" id="bs-clear-cookies">Clear cookies</button>' +
      '<button type="button" class="browser-settings-btn danger" id="bs-clear-all">Clear all browsing data</button>' +
      "</div>" +
      '<p class="browser-settings-status" id="bs-status"></p>' +
      "</section>" +
      '<section class="browser-settings-section">' +
      "<h3>AI / DevTools</h3>" +
      '<label class="browser-settings-check"><input type="checkbox" id="bs-cdp" /> Enable remote debugging (CDP)</label>' +
      '<p class="browser-settings-hint">Off by default so Cloudflare / “verify you are human” works like Chrome. Turn on only for chrome-devtools-mcp — applies on next start.</p>' +
      "</section>" +
      '<section class="browser-settings-section">' +
      "<h3>This site (like Chrome)</h3>" +
      '<div class="browser-settings-secure" id="bs-site">' +
      '<div class="browser-settings-kv"><span>Status</span><strong id="bs-site-status">…</strong></div>' +
      '<div class="browser-settings-kv"><span>Certificate</span><strong id="bs-site-cert">…</strong></div>' +
      '<div class="browser-settings-kv"><span>Host</span><strong id="bs-site-host">…</strong></div>' +
      '<div class="browser-settings-kv"><span>Cookies</span><strong id="bs-site-cookies">…</strong></div>' +
      "</div>" +
      '<p class="browser-settings-hint" id="bs-site-detail"></p>' +
      "</section>" +
      '<section class="browser-settings-section">' +
      "<h3>Security &amp; engine</h3>" +
      '<div class="browser-settings-secure" id="bs-secure">' +
      '<div class="browser-settings-kv"><span>Engine</span><strong id="bs-engine">…</strong></div>' +
      '<div class="browser-settings-kv"><span>Chrome / WebView2</span><strong id="bs-chrome">…</strong></div>' +
      '<div class="browser-settings-kv"><span>Host objects</span><strong>Disabled</strong></div>' +
      '<div class="browser-settings-kv"><span>WebMessage bridge</span><strong>Disabled</strong></div>' +
      '<div class="browser-settings-kv"><span>Bad TLS certs</span><strong>Cancelled (not auto-trusted)</strong></div>' +
      '<div class="browser-settings-kv"><span>App self-embed</span><strong>Blocked</strong></div>' +
      '<div class="browser-settings-kv"><span>Profile isolation</span><strong id="bs-iso">…</strong></div>' +
      "</div>" +
      '<p class="browser-settings-hint">Your system Chrome profile cannot be used here. WebView2 needs its own folder — pointing at Chrome’s User Data corrupts logins and freezes if Chrome is open.</p>' +
      '<ul class="browser-settings-prot" id="bs-prot"></ul>' +
      '<p class="browser-settings-mono" id="bs-profile">…</p>' +
      '<p class="browser-settings-mono" id="bs-ua" style="margin-top:6px"></p>' +
      "</section>" +
      "</div>" +
      '<footer class="browser-settings-foot">' +
      '<button type="button" class="browser-settings-btn primary" id="bs-save">Save</button>' +
      "</footer></div>";

    ensureSettingsCss();
    document.body.appendChild(settingsEl);

    var home = settingsEl.querySelector("#bs-home");
    var searchMount = settingsEl.querySelector("#bs-search");
    var custom = settingsEl.querySelector("#bs-search-custom");
    var customRow = settingsEl.querySelector(".browser-settings-custom");
    home.value = homepage();
    searchEngineValue =
      typeof p.searchEngine === "string" && p.searchEngine ? p.searchEngine : "duckduckgo";
    custom.value = typeof p.searchCustom === "string" ? p.searchCustom : "";
    customRow.style.display = searchEngineValue === "custom" ? "" : "none";
    var cdpEl = settingsEl.querySelector("#bs-cdp");
    if (cdpEl) cdpEl.checked = !!p.enableCdp;

    if (searchChoice) {
      try {
        searchChoice.unmount();
      } catch (_) {}
      searchChoice = null;
    }
    var mountFn =
      (host && host.mountChoiceDropdown) ||
      (window.__duckyPluginHost && window.__duckyPluginHost.mountChoiceDropdown);
    if (mountFn && searchMount) {
      searchChoice = mountFn(searchMount, {
        mode: "radio",
        value: searchEngineValue,
        options: SEARCH_OPTIONS,
        size: "compact",
        "aria-label": "Search engine",
        className: "browser-settings-search-choice",
        onChange: function (next) {
          searchEngineValue = String(next || "duckduckgo");
          customRow.style.display = searchEngineValue === "custom" ? "" : "none";
        },
      });
    } else if (searchMount) {
      // Fallback before host ships mountChoiceDropdown — still radio-styled list.
      searchMount.appendChild(buildFallbackChoice(searchEngineValue, function (next) {
        searchEngineValue = next;
        customRow.style.display = searchEngineValue === "custom" ? "" : "none";
      }));
    }

    renderHistory(history);

    settingsEl.querySelector(".browser-settings-close").addEventListener("click", closeSettings);
    settingsEl.addEventListener("click", function (e) {
      if (e.target === settingsEl) closeSettings();
    });
    settingsEl.querySelector("#bs-save").addEventListener("click", function () {
      var cdp = settingsEl.querySelector("#bs-cdp");
      setPrefs({
        homepage: home.value.trim() || HOMEPAGE_DEFAULT,
        searchEngine: searchEngineValue,
        searchCustom: custom.value.trim(),
        enableCdp: !!(cdp && cdp.checked),
      });
      closeSettings();
    });
    settingsEl.querySelector("#bs-clear-history").addEventListener("click", function () {
      setPrefs({ history: [] });
      renderHistory([]);
      setStatus("History cleared.");
    });
    settingsEl.querySelector("#bs-clear-cache").addEventListener("click", function () {
      clearData("cache");
    });
    settingsEl.querySelector("#bs-clear-cookies").addEventListener("click", function () {
      clearData("cookies");
    });
    settingsEl.querySelector("#bs-clear-all").addEventListener("click", function () {
      clearData("all");
      setPrefs({ history: [] });
      renderHistory([]);
    });

    loadRuntimeInfo();
  }

  function renderHistory(history) {
    var box = settingsEl && settingsEl.querySelector("#bs-history");
    if (!box) return;
    box.innerHTML = "";
    if (!history.length) {
      box.innerHTML = '<p class="browser-settings-hint">No history yet.</p>';
      return;
    }
    history.slice(0, 80).forEach(function (h) {
      var row = document.createElement("button");
      row.type = "button";
      row.className = "browser-settings-hist-row";
      row.innerHTML =
        '<span class="browser-settings-hist-title"></span>' +
        '<span class="browser-settings-hist-url"></span>';
      row.querySelector(".browser-settings-hist-title").textContent = h.title || h.url;
      row.querySelector(".browser-settings-hist-url").textContent = h.url;
      row.addEventListener("click", function () {
        closeSettings();
        if (typeof window.__uefnPanelPush === "function") {
          window.__uefnPanelPush({
            type: "browser_pane_new_window",
            pane_id: TAB_PREFIX,
            url: h.url,
          });
        }
      });
      box.appendChild(row);
    });
  }

  function setStatus(msg) {
    var el = settingsEl && settingsEl.querySelector("#bs-status");
    if (el) el.textContent = msg || "";
  }

  function clearData(kinds) {
    var a = api();
    setStatus("Clearing…");
    if (!a || typeof a.browser_clear_browsing_data !== "function") {
      setStatus("Clear unavailable — update the app for browser_clear_browsing_data.");
      return;
    }
    Promise.resolve(a.browser_clear_browsing_data(kinds))
      .then(function (res) {
        if (res && res.ok) setStatus("Cleared " + kinds + " (" + (res.via || "ok") + ").");
        else setStatus((res && res.error) || "Clear failed.");
      })
      .catch(function (err) {
        setStatus(String(err && err.message ? err.message : err));
      });
  }

  function loadRuntimeInfo() {
    var eng = settingsEl && settingsEl.querySelector("#bs-engine");
    var chrome = settingsEl && settingsEl.querySelector("#bs-chrome");
    var iso = settingsEl && settingsEl.querySelector("#bs-iso");
    var profile = settingsEl && settingsEl.querySelector("#bs-profile");
    var ua = settingsEl && settingsEl.querySelector("#bs-ua");
    var prot = settingsEl && settingsEl.querySelector("#bs-prot");
    var siteStatus = settingsEl && settingsEl.querySelector("#bs-site-status");
    var siteCert = settingsEl && settingsEl.querySelector("#bs-site-cert");
    var siteHost = settingsEl && settingsEl.querySelector("#bs-site-host");
    var siteCookies = settingsEl && settingsEl.querySelector("#bs-site-cookies");
    var siteDetail = settingsEl && settingsEl.querySelector("#bs-site-detail");
    if (profile) {
      profile.textContent = "Profile: %LOCALAPPDATA%\\UEFN-Ducky\\webview2_browser";
    }
    var a = api();
    if (!a) {
      if (eng) eng.textContent = "WebView2 (Chromium)";
      if (chrome) chrome.textContent = "Update the app for live version info";
      if (iso) iso.textContent = "Separate profile (not system Chrome)";
      return;
    }
    var fillRuntime = function (res) {
      if (!res) return;
      if (eng) eng.textContent = res.engine || "WebView2 (Chromium)";
      if (chrome) {
        var ver = res.browser_version || "";
        var major = res.chrome_major ? "Chromium " + res.chrome_major : "";
        chrome.textContent = ver
          ? major + (major ? " · " : "") + ver
          : "Unavailable (open a browser tab once)";
      }
      if (iso) iso.textContent = res.isolation || "Separate UserDataFolder";
      if (profile && res.user_data_dir) profile.textContent = "Profile: " + res.user_data_dir;
      if (ua && res.user_agent) ua.textContent = "UA: " + res.user_agent;
      if (prot && Array.isArray(res.protections)) {
        prot.innerHTML = "";
        res.protections.forEach(function (line) {
          var li = document.createElement("li");
          li.textContent = line;
          prot.appendChild(li);
        });
      }
    };
    if (typeof a.browser_site_security === "function") {
      Promise.resolve(a.browser_site_security(""))
        .then(function (res) {
          if (res && res.runtime) fillRuntime(res.runtime);
          else if (typeof a.browser_runtime_info === "function") {
            return Promise.resolve(a.browser_runtime_info()).then(fillRuntime);
          }
          var site = (res && res.site) || {};
          if (siteStatus) siteStatus.textContent = site.headline || "No active tab";
          if (siteCert) siteCert.textContent = site.certificate || "—";
          if (siteHost) siteHost.textContent = site.host || site.url || "—";
          if (siteCookies) {
            siteCookies.textContent =
              typeof site.cookie_count === "number"
                ? site.cookie_count + " cookie" + (site.cookie_count === 1 ? "" : "s")
                : "—";
          }
          if (siteDetail) siteDetail.textContent = site.detail || "";
          if (prot && Array.isArray(res.protections) && !prot.children.length) {
            res.protections.forEach(function (line) {
              var li = document.createElement("li");
              li.textContent = line;
              prot.appendChild(li);
            });
          }
        })
        .catch(function () {
          if (siteStatus) siteStatus.textContent = "Open a Browser tab to inspect the site";
          if (typeof a.browser_runtime_info === "function") {
            Promise.resolve(a.browser_runtime_info()).then(fillRuntime).catch(function () {});
          }
        });
      return;
    }
    if (typeof a.browser_runtime_info === "function") {
      Promise.resolve(a.browser_runtime_info())
        .then(fillRuntime)
        .catch(function () {
          if (chrome) chrome.textContent = "Could not read engine version";
        });
    }
  }

  function closeSettings() {
    if (searchChoice) {
      try {
        searchChoice.unmount();
      } catch (_) {}
      searchChoice = null;
    }
    if (settingsEl && settingsEl.parentNode) settingsEl.parentNode.removeChild(settingsEl);
    settingsEl = null;
    document.querySelectorAll(".browser-settings-overlay").forEach(function (el) {
      try {
        el.remove();
      } catch (_) {}
    });
    // Only lift cover — never scrub/hide_all (that blacked out every browser tab).
    setBrowserCover(false);
  }

  /** Never leave a full-screen overlay up — that bricks the whole app chrome. */
  function forceCloseSettings() {
    try {
      closeSettings();
    } catch (_) {
      settingsEl = null;
      searchChoice = null;
      setBrowserCover(false);
    }
  }

  /** Same DOM/CSS as core ChoiceDropdown when host mount API is unavailable. */
  function buildFallbackChoice(value, onChange) {
    var wrap = document.createElement("div");
    wrap.className = "choice-dropdown choice-dropdown--compact browser-settings-search-choice";
    var open = false;
    var menu = null;
    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "choice-dropdown-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-label", "Search engine");
    function labelFor(v) {
      for (var i = 0; i < SEARCH_OPTIONS.length; i++) {
        if (SEARCH_OPTIONS[i].value === v) return SEARCH_OPTIONS[i].label;
      }
      return v;
    }
    function paintTrigger() {
      trigger.innerHTML =
        '<span class="choice-dropdown-trigger-copy"><span class="choice-dropdown-trigger-label"></span></span>' +
        '<span class="choice-dropdown-chevron' +
        (open ? " is-open" : "") +
        '" aria-hidden="true"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg></span>';
      trigger.querySelector(".choice-dropdown-trigger-label").textContent = labelFor(value);
      trigger.classList.toggle("is-open", open);
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    function closeMenu() {
      open = false;
      if (menu && menu.parentNode) menu.parentNode.removeChild(menu);
      menu = null;
      paintTrigger();
      document.removeEventListener("mousedown", onOutside, true);
    }
    function onOutside(e) {
      if (wrap.contains(e.target) || (menu && menu.contains(e.target))) return;
      closeMenu();
    }
    function openMenu() {
      closeMenu();
      open = true;
      paintTrigger();
      var rect = trigger.getBoundingClientRect();
      menu = document.createElement("div");
      menu.className = "choice-dropdown-menu";
      menu.setAttribute("role", "radiogroup");
      menu.style.cssText =
        "position:fixed;z-index:100060;left:" +
        rect.left +
        "px;top:" +
        (rect.bottom + 6) +
        "px;min-width:" +
        Math.max(200, rect.width) +
        "px;background:var(--dropdown-bg, #1a1a1e);border:1px solid var(--border);border-radius:var(--radius-sm);box-shadow:0 8px 24px var(--overlay, rgba(0,0,0,.4));";
      SEARCH_OPTIONS.forEach(function (opt) {
        var selected = opt.value === value;
        var row = document.createElement("label");
        row.className = "choice-dropdown-option" + (selected ? " is-selected" : "");
        row.innerHTML =
          '<input type="radio" name="bs-search-fb" value="' +
          opt.value +
          '"' +
          (selected ? " checked" : "") +
          " />" +
          '<span class="choice-dropdown-radio" aria-hidden="true"></span>' +
          '<span class="choice-dropdown-option-copy"><span class="choice-dropdown-option-label"></span></span>';
        row.querySelector(".choice-dropdown-option-label").textContent = opt.label;
        row.addEventListener("click", function (e) {
          e.preventDefault();
          value = opt.value;
          onChange(value);
          closeMenu();
          paintTrigger();
        });
        menu.appendChild(row);
      });
      document.body.appendChild(menu);
      document.addEventListener("mousedown", onOutside, true);
    }
    trigger.addEventListener("click", function () {
      if (open) closeMenu();
      else openMenu();
    });
    paintTrigger();
    wrap.appendChild(trigger);
    return wrap;
  }

  function ensureSettingsCss() {
    if (document.getElementById("browser-plugin-boot-css")) return;
    var style = document.createElement("style");
    style.id = "browser-plugin-boot-css";
    style.textContent =
      ".browser-header-menu .browser-header-settings-btn{border-top:1px solid var(--border-subtle);}" +
      ".browser-header-badge{pointer-events:none;}" +
      ".browser-settings-overlay{position:fixed;inset:0;z-index:200000;background:rgba(0,0,0,.62);" +
      "display:flex;align-items:center;justify-content:center;padding:24px;}" +
      ".browser-settings-modal{width:min(520px,100%);max-height:min(80vh,720px);display:flex;flex-direction:column;" +
      "background:var(--dropdown-bg, #1a1a1e);border:1px solid var(--border, rgba(255,255,255,.1));" +
      "border-radius:10px;box-shadow:0 16px 48px rgba(0,0,0,.45);overflow:hidden;color:var(--text-primary,#ddd);}" +
      ".browser-settings-head{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;" +
      "border-bottom:1px solid var(--border-subtle, rgba(255,255,255,.08));}" +
      ".browser-settings-head h2{margin:0;font-size:14px;font-weight:600;}" +
      ".browser-settings-close{font-size:18px;line-height:1;}" +
      ".browser-settings-body{flex:1;overflow:auto;padding:12px 14px;}" +
      ".browser-settings-section{margin-bottom:18px;}" +
      ".browser-settings-section h3{margin:0 0 8px;font-size:12px;text-transform:uppercase;" +
      "letter-spacing:.04em;color:var(--text-muted,#999);}" +
      ".browser-settings-field{display:flex;flex-direction:column;gap:4px;margin-bottom:8px;font-size:12px;}" +
      ".browser-settings-field>span{color:var(--text-muted,#999);}" +
      ".browser-settings-field input{height:30px;padding:0 10px;border-radius:6px;" +
      "border:1px solid var(--border, rgba(255,255,255,.12));background:rgba(255,255,255,.04);color:inherit;font:inherit;}" +
      ".browser-settings-choice,.browser-settings-search-choice{width:100%;max-width:none;}" +
      ".browser-settings-search-choice .choice-dropdown{width:100%;max-width:none;}" +
      ".browser-settings-hint{margin:0 0 8px;font-size:12px;color:var(--text-muted,#999);line-height:1.4;}" +
      ".browser-settings-check{display:flex;align-items:center;gap:8px;font-size:12px;margin:0 0 8px;cursor:pointer;}" +
      ".browser-settings-check input{margin:0;}" +
      ".browser-settings-mono{margin:0;font-size:11px;font-family:var(--font-mono,ui-monospace,monospace);" +
      "word-break:break-all;color:var(--text-muted,#999);}" +
      ".browser-settings-secure{display:flex;flex-direction:column;gap:6px;margin-bottom:10px;" +
      "padding:10px;border:1px solid var(--border-subtle, rgba(255,255,255,.08));border-radius:8px;" +
      "background:rgba(109,206,160,.06);}" +
      ".browser-settings-kv{display:flex;justify-content:space-between;gap:12px;font-size:12px;}" +
      ".browser-settings-kv span{color:var(--text-muted,#999);flex-shrink:0;}" +
      ".browser-settings-kv strong{font-weight:600;text-align:right;}" +
      ".browser-settings-prot{margin:8px 0 0;padding-left:18px;font-size:11px;color:var(--text-muted,#999);line-height:1.45;}" +
      ".browser-settings-prot li{margin-bottom:4px;}" +
      ".browser-settings-history{max-height:180px;overflow:auto;border:1px solid var(--border-subtle, rgba(255,255,255,.08));" +
      "border-radius:6px;margin-bottom:8px;}" +
      ".browser-settings-hist-row{display:flex;flex-direction:column;align-items:flex-start;gap:2px;width:100%;" +
      "padding:8px 10px;border:none;border-bottom:1px solid var(--border-subtle, rgba(255,255,255,.06));" +
      "background:transparent;color:inherit;font:inherit;text-align:left;cursor:pointer;}" +
      ".browser-settings-hist-row:hover{background:var(--tab-hover, rgba(255,255,255,.06));}" +
      ".browser-settings-hist-title{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;}" +
      ".browser-settings-hist-url{font-size:10px;color:var(--text-muted,#999);overflow:hidden;text-overflow:ellipsis;" +
      "white-space:nowrap;max-width:100%;}" +
      ".browser-settings-actions{display:flex;flex-wrap:wrap;gap:8px;}" +
      ".browser-settings-btn{padding:6px 10px;border-radius:6px;border:1px solid var(--border, rgba(255,255,255,.12));" +
      "background:rgba(255,255,255,.04);color:inherit;font-size:12px;cursor:pointer;}" +
      ".browser-settings-btn:hover{background:var(--tab-hover, rgba(255,255,255,.08));}" +
      ".browser-settings-btn.primary{background:var(--accent, #f5c451);color:#111;border-color:transparent;font-weight:600;}" +
      ".browser-settings-btn.danger{border-color:rgba(255,100,100,.35);color:#ffb4b4;}" +
      ".browser-settings-status{min-height:16px;margin:8px 0 0;font-size:11px;color:var(--text-muted,#999);}" +
      ".browser-settings-foot{padding:10px 14px;border-top:1px solid var(--border-subtle, rgba(255,255,255,.08));" +
      "display:flex;justify-content:flex-end;}";
    document.head.appendChild(style);
  }

  function onOpenSettingsEvent() {
    openSettings();
  }

  function attach() {
    document.addEventListener("click", onTriggerClick, true);
    document.addEventListener("mousedown", onDocDown, true);
    document.addEventListener("keydown", onKey, true);
    window.addEventListener("ducky:browser-settings", onOpenSettingsEvent);
    wrapPanelPush();
    refreshBadge();
    // Throttle: tab chrome mutates a lot; badge only needs a cheap recount.
    var moScheduled = false;
    mo = new MutationObserver(function () {
      if (moScheduled) return;
      moScheduled = true;
      setTimeout(function () {
        moScheduled = false;
        refreshBadge();
      }, 100);
    });
    mo.observe(document.body, { childList: true, subtree: true });
    pollTimer = setInterval(refreshBadge, 1500);
  }

  function cleanup() {
    hideMenu();
    closeSettings(); // also unmounts ChoiceDropdown + lifts UI cover
    document.removeEventListener("click", onTriggerClick, true);
    document.removeEventListener("mousedown", onDocDown, true);
    document.removeEventListener("keydown", onKey, true);
    window.removeEventListener("ducky:browser-settings", onOpenSettingsEvent);
    if (mo) mo.disconnect();
    if (pollTimer) clearInterval(pollTimer);
    var css = document.getElementById("browser-plugin-boot-css");
    if (css) css.remove();
    if (badgeEl && badgeEl.parentNode) badgeEl.parentNode.removeChild(badgeEl);
  }

  window.__duckyPluginBootCleanups = window.__duckyPluginBootCleanups || {};
  window.__duckyPluginBootCleanups[PLUGIN_ID] = cleanup;
  attach();
})();
