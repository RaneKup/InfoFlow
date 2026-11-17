(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const TYPE_META = {
    link: { icon: "", label: "Ссылка", plural: ["ссылка", "ссылки", "ссылок"] },
    note: { icon: "", label: "Заметка", plural: ["заметка", "заметки", "заметок"] },
    file: { icon: "", label: "Файл", plural: ["файл", "файла", "файлов"] },
  };

  const STATUS_META = {
    pending: "В очереди",
    processing: "Обработка…",
    ready: "Готово",
    failed: "Ошибка",
  };

  const MATCH_META = {
    hybrid: "гибрид",
    keyword: "ключевые слова",
    semantic: "по смыслу",
  };

  const SEARCH_MODE_LABELS = {
    hybrid: "Гибрид",
    keyword: "Ключевые слова",
    semantic: "По смыслу",
  };

  const AI_MODE_HINTS = {
    auto: "AI подготовит заголовок, резюме и тематические теги. Текст останется без изменений.",
    tags: "AI подберёт тематические теги, а заголовок и резюме останутся такими, как вы их указали.",
    manual: "Запись сохранится без резюме и автотегов. Заголовок и теги можно задать вручную.",
  };

  const SETTINGS_KEY = "infoflow_settings";
  const DEFAULT_SETTINGS = {
    theme: "dark",
    accent: "graphite",
    font: "normal",
    density: "normal",
    motion: "full",
    aiMode: "auto",
    searchMode: "hybrid",
  };

  const SETTING_VALUES = {
    theme: ["dark", "light", "system"],
    accent: ["graphite", "blue", "green", "amber"],
    font: ["small", "normal", "large"],
    density: ["normal", "compact"],
    motion: ["full", "reduced"],
    aiMode: ["auto", "tags", "manual"],
    searchMode: ["hybrid", "keyword", "semantic"],
  };

  const SETTING_LABELS = {
    theme: { dark: "Тёмная тема", light: "Светлая тема", system: "Системная тема" },
    accent: { graphite: "Акцент: графит", blue: "Акцент: синий", green: "Акцент: зелёный", amber: "Акцент: янтарный" },
    font: { small: "Компактный текст", normal: "Обычный текст", large: "Крупный текст" },
    density: { normal: "Свободная плотность", compact: "Компактная плотность" },
    motion: { full: "Анимации включены", reduced: "Анимации отключены" },
    aiMode: { auto: "Новые записи: с ИИ", tags: "Новые записи: только теги", manual: "Новые записи: вручную" },
    searchMode: { hybrid: "Поиск: гибрид", keyword: "Поиск: ключевые слова", semantic: "Поиск: по смыслу" },
  };

  const LEGAL_DOCS = {
    privacy: {
      title: "Политика конфиденциальности",
      html: `
        <p><strong>Дата обновления:</strong> 17 ноября 2026 года.</p>
        <p>InfoFlow AI — приложение для личной базы знаний. Мы обрабатываем только те данные, которые нужны для работы библиотеки, поиска и синхронизации с Telegram.</p>
        <h3>Какие данные мы храним</h3>
        <ul>
          <li>Адрес электронной почты и хеш пароля для входа в аккаунт.</li>
          <li>Сохранённые ссылки, заметки, файлы, извлечённый текст, заголовки, резюме и теги.</li>
          <li>Технические данные: дата создания записи, статус обработки, идентификатор Telegram при привязке аккаунта.</li>
        </ul>
        <h3>Зачем нужны данные</h3>
        <p>Для аутентификации, отображения библиотеки, поиска по ключевым словам и смыслу, подготовки резюме и тегов, а также для работы Telegram-бота, если вы его используете.</p>
        <h3>AI-обработка</h3>
        <p>Если для записи выбран режим «С ИИ» или «Только теги», текст материала может быть передан настроенному администратором AI-провайдеру исключительно для подготовки резюме или тегов. В режиме «Вручную» материал не отправляется AI-провайдеру.</p>
        <h3>Где хранятся данные</h3>
        <p>Аккаунты и библиотека хранятся в базе данных экземпляра InfoFlow AI. Настройки темы и интерфейса сохраняются только в localStorage вашего браузера. Токен входа также хранится в localStorage.</p>
        <h3>Передача третьим лицам</h3>
        <p>Мы не продаём и не передаём ваши данные для рекламы. Передача возможна только техническим поставщикам, необходимым для работы сервиса, или по требованию закона.</p>
        <h3>Хранение и удаление</h3>
        <p>Данные хранятся до удаления записи или аккаунта. Записи можно удалить в интерфейсе. Для удаления аккаунта обратитесь к администратору вашего экземпляра InfoFlow AI.</p>
        <h3>Ваши права</h3>
        <p>Вы можете просматривать, исправлять и удалять свои записи, менять теги и настройки. Вы также вправе запросить информацию об обработке ваших данных у администратора сервиса.</p>
        <h3>Изменения политики</h3>
        <p>Актуальная версия политики всегда доступна по ссылке внизу сайта. При существенных изменениях мы обновим дату документа.</p>
      `,
    },
    terms: {
      title: "Условия использования",
      html: `
        <p><strong>Дата обновления:</strong> 17 ноября 2026 года.</p>
        <p>Используя InfoFlow AI, вы соглашаетесь с настоящими условиями. Если вы не согласны с ними, пожалуйста, не используйте сервис.</p>
        <h3>Назначение сервиса</h3>
        <p>InfoFlow AI помогает сохранять ссылки, заметки и файлы, формировать личную библиотеку и искать в ней информацию. Сервис предоставляется как есть и может развиваться.</p>
        <h3>Аккаунт и безопасность</h3>
        <p>Вы отвечаете за сохранность пароля и действия в своём аккаунте. Не передавайте учётные данные третьим лицам. Сообщите администратору, если заметили несанкционированный доступ.</p>
        <h3>Ваш контент</h3>
        <p>Права на сохранённые материалы остаются у вас или их законных правообладателей. Вы подтверждаете, что имеете право сохранять и обрабатывать загружаемый контент. Не загружайте материалы, нарушающие закон или права других людей.</p>
        <h3>AI-функции</h3>
        <p>Резюме и теги формируются автоматически и могут содержать ошибки. Проверяйте важную информацию и используйте AI-результаты как вспомогательные, а не как единственный источник истины.</p>
        <h3>Допустимое использование</h3>
        <ul>
          <li>Не пытайтесь получить доступ к чужим аккаунтам или данным.</li>
          <li>Не нарушайте работу сервиса, не обходите ограничения и не создавайте чрезмерную нагрузку.</li>
          <li>Не используйте сервис для распространения незаконного или вредоносного контента.</li>
        </ul>
        <h3>Доступность и ответственность</h3>
        <p>Мы стремимся поддерживать стабильную работу, но не гарантируем непрерывный доступ и сохранность данных при сбоях инфраструктуры. Делайте резервные копии важных материалов.</p>
        <h3>Изменения условий</h3>
        <p>Условия могут обновляться вместе с развитием сервиса. Актуальная версия публикуется внизу сайта.</p>
        <h3>Применимое право</h3>
        <p>Вопросы, не урегулированные настоящими условиями, решаются в соответствии с применимым законодательством и правилами администратора экземпляра InfoFlow AI.</p>
      `,
    },
  };

  function loadSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
      const settings = { ...DEFAULT_SETTINGS };
      for (const [key, allowed] of Object.entries(SETTING_VALUES)) {
        if (allowed.includes(saved[key])) settings[key] = saved[key];
      }
      return settings;
    } catch (_error) {
      return { ...DEFAULT_SETTINGS };
    }
  }

  const state = {
    token: localStorage.getItem("infoflow_token") || "",
    user: null,
    settings: loadSettings(),
    type: "",
    tag: null,
    query: "",
    mode: "hybrid",
    items: [],
    total: 0,
    offset: 0,
    limit: 12,
    loading: false,
    pollTimer: null,
    composer: "link",
    toastTimer: null,
    modalId: null,
    modalItem: null,
  };

  function formatError(payload, fallback) {
    if (!payload) return fallback;
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((entry) => {
          const field = (entry.loc || []).filter((part) => part !== "body").join(".");
          return field ? `${field}: ${entry.msg}` : entry.msg;
        })
        .join("; ");
    }
    return fallback;
  }

  async function api(path, options = {}) {
    const { method = "GET", body = null, form = false, auth = true } = options;
    const headers = {};
    if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;

    let payload = body;
    if (body && !form) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }

    const response = await fetch(`/api${path}`, { method, headers, body: payload });
    if (response.status === 401 && auth) {
      handleUnauthorized();
      const authError = new Error("Сессия истекла. Войдите снова.");
      authError.status = 401;
      throw authError;
    }
    if (!response.ok) {
      let parsed = null;
      try {
        parsed = await response.json();
      } catch (_error) {
        }
      const requestError = new Error(formatError(parsed, `Ошибка ${response.status}`));
      requestError.status = response.status;
      throw requestError;
    }
    if (response.status === 204) return null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) return response.json();
    return response;
  }

  function handleUnauthorized() {
    state.token = "";
    state.user = null;
    localStorage.removeItem("infoflow_token");
    localStorage.removeItem("infoflow_email");
    showAuth();
  }

  function plural(count, one, few, many) {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  }

  function formatDate(value) {
    if (!value) return "";
    const normalized =
      /Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function parseTags(raw) {
    return (raw || "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean)
      .slice(0, 20);
  }

  function formatSize(bytes) {
    if (!bytes) return "";
    const units = ["Б", "КБ", "МБ", "ГБ"];
    let value = bytes;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    const digits = index === 0 || value >= 10 ? 0 : 1;
    return `${value.toFixed(digits)} ${units[index]}`;
  }

  function toast(message, kind = "") {
    const node = $("#toast");
    node.textContent = message;
    node.className = `toast is-visible${kind ? ` is-${kind}` : ""}`;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      node.classList.remove("is-visible");
    }, 3800);
  }

  function setBusy(element, busy, busyText = "Сохраняю…") {
    if (!element) return;
    if (busy) {
      element.dataset.originalText = element.textContent;
      element.textContent = busyText;
      element.disabled = true;
    } else {
      element.textContent = element.dataset.originalText || element.textContent;
      element.disabled = false;
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
    } catch (_error) {
      }
  }

  function resolvedTheme() {
    if (state.settings.theme !== "system") return state.settings.theme;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function applySettings() {
    const settings = state.settings;
    const root = document.documentElement;
    const theme = resolvedTheme();
    root.dataset.theme = theme;
    root.dataset.accent = settings.accent;
    root.dataset.font = settings.font;
    root.dataset.density = settings.density;
    root.dataset.motion = settings.motion;
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.content = theme === "light" ? "#f6f6f2" : "#070707";
    syncSettingsUI();
  }

  function syncSettingsUI() {
    $$("[data-setting]").forEach((group) => {
      const key = group.dataset.setting;
      $$("[data-value]", group).forEach((button) => {
        const active = button.dataset.value === state.settings[key];
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    });
  }

  function setSearchMode(mode, { persist = false } = {}) {
    const next = SEARCH_MODE_LABELS[mode] ? mode : "hybrid";
    state.mode = next;
    const select = $("#search-mode");
    if (select) select.value = next;
    if (persist) {
      state.settings.searchMode = next;
      saveSettings();
      syncSettingsUI();
    }
  }

  function currentAiMode() {
    return $('input[name="ai-mode"]:checked')?.value || state.settings.aiMode || "auto";
  }

  function setComposerAiMode(mode) {
    const next = AI_MODE_HINTS[mode] ? mode : "auto";
    $$('input[name="ai-mode"]').forEach((input) => {
      input.checked = input.value === next;
    });
    updateAiModeHint();
  }

  function updateAiModeHint() {
    const mode = currentAiMode();
    const note = $("#ai-choice-note");
    if (note) note.textContent = AI_MODE_HINTS[mode] || AI_MODE_HINTS.auto;
    const noteBottom = $("#composer-note");
    if (noteBottom) {
      noteBottom.textContent =
        mode === "manual"
          ? "Материал будет сохранён без AI-резюме и автоматических тегов."
          : mode === "tags"
            ? "AI подберёт только теги. Заголовок и резюме останутся вашими."
            : "AI сделает резюме, подберёт теги и сохранит материал для поиска по смыслу.";
    }
  }

  function openSettings() {
    const modal = $("#settings-modal");
    if (!modal) return;
    syncSettingsUI();
    modal.classList.remove("is-hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("is-locked");
    $(".modal__close", modal)?.focus();
  }

  function closeSettings() {
    const modal = $("#settings-modal");
    if (!modal) return;
    modal.classList.add("is-hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-locked");
  }

  function closeLegal() {
    const modal = $("#legal-modal");
    if (!modal) return;
    modal.classList.add("is-hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-locked");
  }

  function openLegal(kind) {
    const doc = LEGAL_DOCS[kind] || LEGAL_DOCS.privacy;
    const modal = $("#legal-modal");
    if (!modal) return;
    $("#legal-title").textContent = doc.title;
    $("#legal-body").innerHTML = doc.html;
    $("#legal-body").scrollTop = 0;
    modal.classList.remove("is-hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("is-locked");
    $(".modal__close", modal)?.focus();
  }

  // Делегирование на уровне документа: правовые окна открываются даже если
  // какой-то другой обработчик не привязался.
  document.addEventListener("click", (event) => {
    const legalButton = event.target.closest("[data-legal]");
    if (legalButton) {
      event.preventDefault();
      openLegal(legalButton.dataset.legal);
      return;
    }
    if (event.target.closest("[data-legal-close]")) closeLegal();
  });

  function showAuth() {
    closeModal();
    closeSettings();
    closeLegal();
    $("#app-screen").classList.add("is-hidden");
    $("#auth-screen").classList.remove("is-hidden");
    $("#login-error").textContent = "";
    $("#register-error").textContent = "";
  }

  function showApp() {
    $("#auth-screen").classList.add("is-hidden");
    $("#app-screen").classList.remove("is-hidden");
    $("#user-email").textContent =
      state.user?.email || localStorage.getItem("infoflow_email") || "";
    setSearchMode(state.settings.searchMode);
    setComposerAiMode(state.settings.aiMode);
    loadAll();
  }

  async function handleAuthSubmit(event, mode) {
    event.preventDefault();
    const form = event.currentTarget;
    const errorNode = mode === "login" ? $("#login-error") : $("#register-error");
    errorNode.textContent = "";
    const button = $("button[type=submit]", form);
    const data = new FormData(form);
    setBusy(button, true, mode === "login" ? "Вхожу…" : "Создаю…");
    try {
      const result = await api(`/auth/${mode}`, {
        method: "POST",
        auth: false,
        body: {
          email: String(data.get("email") || "").trim(),
          password: String(data.get("password") || ""),
        },
      });
      state.token = result.access_token;
      state.user = result.user;
      localStorage.setItem("infoflow_token", state.token);
      localStorage.setItem("infoflow_email", state.user?.email || "");
      form.reset();
      showApp();
      toast(mode === "login" ? "С возвращением!" : "Аккаунт создан", "success");
    } catch (error) {
      errorNode.textContent = error.message;
    } finally {
      setBusy(button, false);
    }
  }

  function logout() {
    state.token = "";
    state.user = null;
    state.items = [];
    state.query = "";
    state.tag = null;
    state.type = "";
    localStorage.removeItem("infoflow_token");
    localStorage.removeItem("infoflow_email");
    clearTimeout(state.pollTimer);
    closeModal();
    $("#search-input").value = "";
    $("#items-grid").innerHTML = "";
    showAuth();
  }

  async function loadAll() {
    await Promise.allSettled([loadItems({ reset: true }), loadTags(), loadStats()]);
  }

  function skeleton() {
    return Array.from({ length: 3 })
      .map(() => '<div class="item-card skeleton-card" aria-hidden="true"></div>')
      .join("");
  }

  async function loadItems({ reset = true, silent = false } = {}) {
    if (state.loading) return;
    state.loading = true;
    const grid = $("#items-grid");
    if (reset && !silent) {
      grid.innerHTML = skeleton();
      $("#empty-state").classList.add("is-hidden");
    }

    try {
      if (state.query) {
        const params = new URLSearchParams({
          q: state.query,
          mode: state.mode,
          limit: "50",
        });
        if (state.type) params.set("type", state.type);
        if (state.tag) params.set("tag", state.tag);
        const data = await api(`/search?${params.toString()}`);
        state.items = data.results;
        state.total = data.total;
        state.offset = data.results.length;
        $("#search-meta").textContent = `${data.total} ${plural(
          data.total,
          "результат",
          "результата",
          "результатов"
        )} · ${data.took_ms} мс`;
        $("#search-meta").classList.remove("is-hidden");
        renderItems(true);
      } else {
        const params = new URLSearchParams({
          limit: String(state.limit),
          offset: String(reset ? 0 : state.offset),
        });
        if (state.type) params.set("type", state.type);
        if (state.tag) params.set("tag", state.tag);
        const data = await api(`/items?${params.toString()}`);
        state.items = reset ? data.items : [...state.items, ...data.items];
        state.total = data.total;
        state.offset = (reset ? 0 : state.offset) + data.items.length;
        $("#search-meta").classList.add("is-hidden");
        renderItems(false);
      }
    } catch (error) {
      if (!silent) toast(error.message, "error");
    } finally {
      state.loading = false;
      updateLibraryHead();
      updateLoadMore();
      schedulePoll();
    }
  }

  async function loadTags() {
    try {
      const tags = await api("/tags");
      renderTags(tags);
    } catch (error) {
      if (state.token) toast(error.message, "error");
    }
  }

  async function loadStats() {
    try {
      const stats = await api("/stats");
      $("#stat-total").textContent = String(stats.total_items);
      $("#stat-tags").textContent = String(stats.tags_count);
      $("#stat-ready").textContent = String(stats.by_status?.ready || 0);
    } catch (_error) {
      }
  }

  function schedulePoll() {
    clearTimeout(state.pollTimer);
    const active = state.items.some((item) =>
      ["pending", "processing"].includes(item.status)
    );
    if (!active || !state.token) return;
    state.pollTimer = setTimeout(async () => {
      await loadItems({ reset: true, silent: true });
      await Promise.allSettled([loadTags(), loadStats()]);
      if (
        state.modalId &&
        state.modalItem &&
        ["pending", "processing"].includes(state.modalItem.status)
      ) {
        await reloadModal();
      }
    }, 2600);
  }

  function updateLibraryHead() {
    let title = "Моя библиотека";
    if (state.query) title = "Результаты поиска";
    else if (state.type) title = TYPE_META[state.type]?.label || "Библиотека";
    if (state.tag) title += ` · #${state.tag}`;
    $("#items-title").textContent = title;

    const count = state.total;
    const word = state.query
      ? plural(count, "результат", "результата", "результатов")
      : plural(count, "запись", "записи", "записей");
    $("#items-count").textContent = `${count} ${word}`;

    const empty = $("#empty-state");
    const visible = !state.loading && state.items.length === 0;
    empty.classList.toggle("is-hidden", !visible);
    if (visible) {
      $("h3", empty).textContent = state.query
        ? "Ничего не найдено"
        : state.tag || state.type
          ? "В этой подборке пока пусто"
          : "Пока пусто";
      $("p", empty).textContent = state.query
        ? "Попробуйте переформулировать запрос или переключите режим поиска."
        : "Сохраните первую ссылку, заметку или файл — и InfoFlow начнёт собирать вашу базу знаний.";
    }
  }

  function updateLoadMore() {
    const button = $("#load-more");
    const show =
      !state.query && state.items.length > 0 && state.items.length < state.total;
    button.classList.toggle("is-hidden", !show);
  }

  function renderTags(tags) {
    const container = $("#tag-list");
    container.replaceChildren();
    $("#clear-tag").classList.toggle("is-hidden", !state.tag);

    if (!tags.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Теги появятся после первой записи";
      container.append(empty);
      return;
    }

    for (const tag of tags) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tag-chip";
      button.dataset.tag = tag.name;
      button.textContent = `#${tag.name}`;
      if (tag.name === state.tag) button.classList.add("is-active");
      const count = document.createElement("small");
      count.textContent = String(tag.items_count);
      button.append(count);
      container.append(button);
    }
  }

  function renderItems(withSearchMeta) {
    const grid = $("#items-grid");
    grid.replaceChildren();
    const template = $("#item-template");

    for (const item of state.items) {
      const node = template.content.firstElementChild.cloneNode(true);
      node.dataset.id = String(item.id);
      const meta = TYPE_META[item.type] || { icon: "•", label: "Запись" };

      $(".type-icon", node).textContent = meta.icon;
      $(".type-label", node).textContent = meta.label;

      const status = $(".status-badge", node);
      status.textContent = STATUS_META[item.status] || item.status;
      status.dataset.status = item.status;
      status.classList.toggle("is-hidden", item.status === "ready");
      if (item.error_message) status.title = item.error_message;

      const match = $(".match-badge", node);
      if (withSearchMeta && item.match) {
        match.textContent = MATCH_META[item.match] || item.match;
        match.classList.remove("is-hidden");
      } else {
        match.classList.add("is-hidden");
      }

      const title = $(".item-title", node);
      title.textContent = item.title || "Без названия";

      const summary = $(".item-summary", node);
      let summaryText = item.snippet || item.summary;
      if (!summaryText && ["pending", "processing"].includes(item.status)) {
        summaryText = "AI готовит резюме и теги…";
      }
      if (!summaryText && item.ai_mode === "manual") {
        summaryText = "Ручная запись без AI-резюме и автоматических тегов.";
      } else if (!summaryText && item.ai_mode === "tags") {
        summaryText = "AI подобрал теги, резюме для этой записи не создавалось.";
      }
      summary.textContent = summaryText || "Описание пока недоступно.";

      const tags = $(".item-tags", node);
      for (const tag of item.tags || []) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = `item-tag${tag.is_auto_generated ? "" : " is-manual"}`;
        chip.dataset.tag = tag.name;
        chip.textContent = `#${tag.name}`;
        tags.append(chip);
      }

      $(".item-date", node).textContent = formatDate(item.created_at);

      const openLink = $(".open-link", node);
      if (item.type === "link" && item.original_url) {
        openLink.href = item.original_url;
        openLink.classList.remove("is-hidden");
      } else {
        openLink.classList.add("is-hidden");
      }

      const download = $(".download", node);
      if (item.type === "file") {
        download.classList.remove("is-hidden");
      } else {
        download.classList.add("is-hidden");
      }

      const reprocess = $(".reprocess", node);
      reprocess.disabled = ["pending", "processing"].includes(item.status);

      grid.append(node);
    }

    updateLibraryHead();
  }

  async function deleteItem(id) {
    const item = state.items.find((entry) => entry.id === id);
    const label = item?.title ? `«${item.title}»` : "эту запись";
    if (!confirm(`Удалить ${label}? Действие необратимо.`)) return false;
    try {
      await api(`/items/${id}`, { method: "DELETE" });
      state.items = state.items.filter((entry) => entry.id !== id);
      state.total = Math.max(0, state.total - 1);
      renderItems(Boolean(state.query));
      toast("Запись удалена", "success");
      await Promise.allSettled([loadTags(), loadStats()]);
      return true;
    } catch (error) {
      toast(error.message, "error");
      return false;
    }
  }

  async function reprocessItem(id) {
    try {
      await api(`/items/${id}/reprocess`, { method: "POST" });
      const item = state.items.find((entry) => entry.id === id);
      if (item) item.status = "pending";
      if (state.modalItem?.id === id) state.modalItem.status = "pending";
      renderItems(Boolean(state.query));
      toast("AI переобрабатывает запись…");
      schedulePoll();
      return true;
    } catch (error) {
      toast(error.message, "error");
      return false;
    }
  }

  async function downloadItem(id) {
    const item = state.items.find((entry) => entry.id === id);
    try {
      const response = await fetch(`/api/items/${id}/download`, {
        headers: { Authorization: `Bearer ${state.token}` },
      });
      if (!response.ok) throw new Error("Не удалось скачать файл");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = item?.file_name || `infoflow-${id}`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast(error.message, "error");
    }
  }

  function closeModal() {
    state.modalId = null;
    state.modalItem = null;
    const modal = $("#item-modal");
    modal.classList.add("is-hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-locked");
  }

  function renderModalTags(item) {
    const container = $("#modal-tags");
    container.replaceChildren();
    for (const tag of item.tags || []) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `item-tag${tag.is_auto_generated ? "" : " is-manual"}`;
      chip.dataset.modalTag = tag.name;
      chip.title = tag.is_auto_generated ? "Автотег — нажмите, чтобы отфильтровать" : "Ручной тег";
      chip.textContent = `#${tag.name}`;
      container.append(chip);
    }
    $("#modal-tags-input").value = (item.tags || []).map((tag) => tag.name).join(", ");
  }

  function renderModal(item) {
    const meta = TYPE_META[item.type] || { icon: "•", label: "Запись" };
    $("#modal-type-icon").textContent = meta.icon;
    $("#modal-type-label").textContent = meta.label;

    const status = $("#modal-status");
    status.textContent = STATUS_META[item.status] || item.status;
    status.dataset.status = item.status;
    status.classList.toggle("is-hidden", item.status === "ready");
    status.title = item.error_message || "";

    $("#modal-title").textContent = item.title || "Без названия";

    const metaParts = [];
    const date = formatDate(item.created_at);
    if (date) metaParts.push(date);
    if (item.type === "file" && item.file_name) {
      metaParts.push(
        `${item.file_name}${item.file_size ? ` · ${formatSize(item.file_size)}` : ""}`
      );
    }
    if (item.original_url) {
      try {
        metaParts.push(new URL(item.original_url).hostname.replace(/^www\./, ""));
      } catch (_error) {
        }
    }
    $("#modal-meta").textContent = metaParts.join(" · ");

    const summary = $("#modal-summary");
    if (item.summary) {
      summary.textContent = item.summary;
    } else {
      summary.textContent = ["pending", "processing"].includes(item.status)
        ? "AI готовит резюме и теги…"
        : item.ai_mode === "manual"
          ? "Для этой записи AI-резюме отключено — текст сохранён в том виде, в котором вы его добавили."
          : item.ai_mode === "tags"
            ? "Для этой записи AI создавал только теги, без резюме."
            : "Резюме пока нет.";
    }

    const content = $("#modal-content");
    const text = (item.content_text || "").trim();
    if (text) {
      content.textContent = text;
      content.classList.remove("is-empty");
    } else {
      content.textContent = ["pending", "processing"].includes(item.status)
        ? "Материал ещё обрабатывается. Полный текст появится после завершения."
        : item.type === "file"
          ? "Полный текст не извлечён. Скачайте исходный файл кнопкой ниже."
          : item.type === "link"
            ? "Не удалось извлечь текст страницы. Откройте источник по ссылке ниже."
            : "Полный текст не сохранён.";
      content.classList.add("is-empty");
    }
    $("#modal-copy").disabled = !text;

    renderModalTags(item);

    const openLink = $("#modal-open-link");
    if (item.type === "link" && item.original_url) {
      openLink.href = item.original_url;
      openLink.classList.remove("is-hidden");
    } else {
      openLink.removeAttribute("href");
      openLink.classList.add("is-hidden");
    }
    $("#modal-download").classList.toggle("is-hidden", item.type !== "file");
    $("#modal-reprocess").disabled = ["pending", "processing"].includes(item.status);
  }

  async function openItemModal(id) {
    state.modalId = id;
    state.modalItem = null;
    const modal = $("#item-modal");
    modal.classList.remove("is-hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("is-locked");

    const cached = state.items.find((entry) => entry.id === id);
    $("#modal-title").textContent = cached?.title || "Загрузка…";
    $("#modal-meta").textContent = "";
    $("#modal-summary").textContent = "Загрузка…";
    $("#modal-content").textContent = "";
    $("#modal-content").classList.remove("is-empty");
    $("#modal-tags").replaceChildren();
    $("#modal-tags-input").value = "";
    $("#modal-copy").disabled = true;
    $("#modal-scroll").scrollTop = 0;

    try {
      const item = await api(`/items/${id}`);
      if (state.modalId !== id) return;
      state.modalItem = item;
      renderModal(item);
      $(".modal__close")?.focus();
    } catch (error) {
      if (state.modalId === id) {
        closeModal();
        toast(error.message, "error");
      }
    }
  }

  async function reloadModal() {
    const id = state.modalId;
    if (!id) return;
    try {
      const item = await api(`/items/${id}`);
      if (state.modalId !== id) return;
      state.modalItem = item;
      renderModal(item);
    } catch (_error) {
      }
  }

  async function saveModalTags(event) {
    event.preventDefault();
    const id = state.modalId;
    if (!id) return;
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    const tags = parseTags($("#modal-tags-input").value);
    setBusy(button, true, "Сохраняю…");
    try {
      const updated = await api(`/items/${id}`, {
        method: "PATCH",
        body: { tags, replace_tags: true },
      });
      state.modalItem = updated;
      const cached = state.items.find((entry) => entry.id === id);
      if (cached) cached.tags = updated.tags;
      renderModal(updated);
      toast("Теги обновлены", "success");
      await Promise.allSettled([loadTags(), loadStats()]);
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function copyModalContent() {
    const text = (state.modalItem?.content_text || "").trim();
    if (!text) {
      toast("Нет текста для копирования");
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.append(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      toast("Текст скопирован", "success");
    } catch (_error) {
      toast("Не удалось скопировать текст", "error");
    }
  }

  async function deleteFromModal() {
    const id = state.modalId;
    if (!id) return;
    const deleted = await deleteItem(id);
    if (deleted) closeModal();
  }

  async function reprocessFromModal() {
    const id = state.modalId;
    if (!id) return;
    const ok = await reprocessItem(id);
    if (ok && state.modalItem) {
      state.modalItem.status = "pending";
      renderModal(state.modalItem);
    }
  }

  async function saveLink(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    $("#composer-error").textContent = "";
    setBusy(button, true);

    const data = new FormData(form);
    const aiMode = currentAiMode();
    try {
      await api("/items", {
        method: "POST",
        body: {
          type: "link",
          url: String(data.get("url") || "").trim(),
          title: String(data.get("title") || "").trim() || null,
          tags: parseTags(String(data.get("tags") || "")),
          ai_mode: aiMode,
        },
      });
      form.reset();
      toast(
        aiMode === "manual"
          ? "Ссылка сохранена без AI-обработки"
          : aiMode === "tags"
            ? "Сохранено. AI подбирает теги…"
            : "Сохранено. AI делает резюме и теги…",
        "success"
      );
      await loadAll();
    } catch (error) {
      $("#composer-error").textContent = error.message;
    } finally {
      setBusy(button, false);
    }
  }

  async function saveNote(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    $("#composer-error").textContent = "";
    setBusy(button, true);

    const data = new FormData(form);
    const aiMode = currentAiMode();
    try {
      await api("/items", {
        method: "POST",
        body: {
          type: "note",
          text: String(data.get("text") || "").trim(),
          title: String(data.get("title") || "").trim() || null,
          tags: parseTags(String(data.get("tags") || "")),
          ai_mode: aiMode,
        },
      });
      form.reset();
      toast(
        aiMode === "manual"
          ? "Заметка сохранена вручную"
          : aiMode === "tags"
            ? "Заметка сохранена. AI подбирает теги…"
            : "Заметка сохранена. AI уже работает…",
        "success"
      );
      await loadAll();
    } catch (error) {
      $("#composer-error").textContent = error.message;
    } finally {
      setBusy(button, false);
    }
  }

  async function saveFile(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    const input = $("#file-input");
    $("#composer-error").textContent = "";

    if (!input.files || !input.files.length) {
      $("#composer-error").textContent = "Выберите файл для загрузки";
      return;
    }

    const data = new FormData();
    const aiMode = currentAiMode();
    data.append("file", input.files[0]);
    data.append("title", String(new FormData(form).get("title") || ""));
    data.append("tags", String(new FormData(form).get("tags") || ""));
    data.append("ai_mode", aiMode);

    setBusy(button, true, "Загружаю…");
    try {
      await api("/items/upload", { method: "POST", body: data, form: true });
      form.reset();
      $("#dropzone-title").textContent = "Перетащите файл или нажмите";
      toast(
        aiMode === "manual"
          ? "Файл загружен без AI-обработки"
          : aiMode === "tags"
            ? "Файл загружен. AI подбирает теги…"
            : "Файл загружен. AI извлекает текст…",
        "success"
      );
      await loadAll();
    } catch (error) {
      $("#composer-error").textContent = error.message;
    } finally {
      setBusy(button, false);
    }
  }

  function updateFileLabel() {
    const input = $("#file-input");
    $("#dropzone-title").textContent =
      input.files && input.files.length ? input.files[0].name : "Перетащите файл или нажмите";
  }

  function bindEvents() {
    $$("[data-auth-tab]").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$("[data-auth-tab]").forEach((node) => node.classList.remove("is-active"));
        tab.classList.add("is-active");
        const mode = tab.dataset.authTab;
        $("#login-form").classList.toggle("is-hidden", mode !== "login");
        $("#register-form").classList.toggle("is-hidden", mode !== "register");
        $("#login-error").textContent = "";
        $("#register-error").textContent = "";
      });
    });

    $("#login-form").addEventListener("submit", (event) => handleAuthSubmit(event, "login"));
    $("#register-form").addEventListener("submit", (event) => handleAuthSubmit(event, "register"));
    $("#logout-btn").addEventListener("click", logout);

    $("#settings-btn").addEventListener("click", openSettings);
    $("#settings-modal").addEventListener("click", (event) => {
      if (event.target.closest("[data-settings-close]")) {
        closeSettings();
        return;
      }
      const group = event.target.closest("[data-setting]");
      const button = event.target.closest("[data-value]");
      if (!group || !button) return;
      const key = group.dataset.setting;
      const value = button.dataset.value;
      if (!SETTING_VALUES[key]?.includes(value)) return;
      state.settings[key] = value;
      saveSettings();
      applySettings();
      if (key === "aiMode") setComposerAiMode(value);
      if (key === "searchMode") {
        setSearchMode(value);
        if (state.query) loadItems({ reset: true });
      }
      const label = SETTING_LABELS[key]?.[value];
      if (label) toast(label, "success");
    });

    $("#settings-reset").addEventListener("click", () => {
      state.settings = { ...DEFAULT_SETTINGS };
      saveSettings();
      applySettings();
      setComposerAiMode(state.settings.aiMode);
      setSearchMode(state.settings.searchMode);
      if (state.query) loadItems({ reset: true });
      toast("Настройки сброшены", "success");
    });

    $$('input[name="ai-mode"]').forEach((input) => {
      input.addEventListener("change", updateAiModeHint);
    });

    $$("[data-composer]").forEach((tab) => {
      tab.addEventListener("click", () => {
        state.composer = tab.dataset.composer;
        $$("[data-composer]").forEach((node) => node.classList.remove("is-active"));
        tab.classList.add("is-active");
        $("#link-form").classList.toggle("is-hidden", state.composer !== "link");
        $("#note-form").classList.toggle("is-hidden", state.composer !== "note");
        $("#file-form").classList.toggle("is-hidden", state.composer !== "file");
        $("#composer-error").textContent = "";
      });
    });

    $("#link-form").addEventListener("submit", saveLink);
    $("#note-form").addEventListener("submit", saveNote);
    $("#file-form").addEventListener("submit", saveFile);

    $("#file-input").addEventListener("change", updateFileLabel);
    const dropzone = $("#dropzone");
    ["dragenter", "dragover"].forEach((name) =>
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.add("is-dragover");
      })
    );
    ["dragleave", "drop"].forEach((name) =>
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.remove("is-dragover");
      })
    );
    dropzone.addEventListener("drop", (event) => {
      const files = event.dataTransfer?.files;
      if (files && files.length) {
        $("#file-input").files = files;
        updateFileLabel();
      }
    });

    $$("[data-type]").forEach((button) => {
      button.addEventListener("click", () => {
        state.type = button.dataset.type || "";
        $$("[data-type]").forEach((node) => node.classList.remove("is-active"));
        button.classList.add("is-active");
        loadItems({ reset: true });
      });
    });

    $("#tag-list").addEventListener("click", (event) => {
      const chip = event.target.closest("[data-tag]");
      if (!chip) return;
      state.tag = state.tag === chip.dataset.tag ? null : chip.dataset.tag;
      loadTags();
      loadItems({ reset: true });
    });

    $("#clear-tag").addEventListener("click", () => {
      state.tag = null;
      loadTags();
      loadItems({ reset: true });
    });

    $("#items-grid").addEventListener("click", (event) => {
      const card = event.target.closest(".item-card");
      if (!card) return;
      const id = Number(card.dataset.id);
      if (event.target.closest(".delete")) {
        deleteItem(id);
        return;
      }
      if (event.target.closest(".reprocess")) {
        reprocessItem(id);
        return;
      }
      if (event.target.closest(".download")) {
        downloadItem(id);
        return;
      }
      const tag = event.target.closest("[data-tag]");
      if (tag) {
        state.tag = tag.dataset.tag;
        loadTags();
        loadItems({ reset: true });
        return;
      }
      if (event.target.closest("a")) return;
      openItemModal(id);
    });

    $("#item-modal").addEventListener("click", (event) => {
      if (event.target.closest("[data-modal-close]")) {
        closeModal();
        return;
      }
      const chip = event.target.closest("[data-modal-tag]");
      if (chip) {
        state.tag = chip.dataset.modalTag;
        closeModal();
        loadTags();
        loadItems({ reset: true });
      }
    });

    $("#modal-tags-form").addEventListener("submit", saveModalTags);
    $("#modal-copy").addEventListener("click", copyModalContent);
    $("#modal-download").addEventListener("click", () => {
      if (state.modalId) downloadItem(state.modalId);
    });
    $("#modal-reprocess").addEventListener("click", reprocessFromModal);
    $("#modal-delete").addEventListener("click", deleteFromModal);

    let searchTimer = null;
    $("#search-input").addEventListener("input", (event) => {
      const value = event.target.value.trim();
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.query = value;
        loadItems({ reset: true });
      }, 320);
    });

    const searchSelect = $("#search-mode");
    searchSelect.addEventListener("change", (event) => {
      setSearchMode(event.target.value, { persist: true });
      if (state.query) loadItems({ reset: true });
    });

    $("#refresh-btn").addEventListener("click", () => {
      loadAll();
      toast("Обновлено");
    });

    $("#load-more").addEventListener("click", () => {
      loadItems({ reset: false });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!$("#settings-modal").classList.contains("is-hidden")) {
          closeSettings();
          return;
        }
        if (!$("#legal-modal").classList.contains("is-hidden")) {
          closeLegal();
          return;
        }
        if (state.modalId) {
          closeModal();
          return;
        }
        const input = $("#search-input");
        if (document.activeElement === input && input.value) {
          input.value = "";
          state.query = "";
          loadItems({ reset: true });
        }
      }
    });
  }

  async function init() {
    applySettings();
    bindEvents();
    window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
      if (state.settings.theme === "system") applySettings();
    });
    if (!state.token) {
      showAuth();
      return;
    }
    // Показываем интерфейс сразу: обновление страницы не должно выглядеть
    // как выход из аккаунта. Если токен действительно истёк, придёт 401
    // и пользователь вернётся на экран входа.
    showApp();
    try {
      state.user = await api("/auth/me");
      localStorage.setItem("infoflow_email", state.user?.email || "");
      $("#user-email").textContent = state.user?.email || "";
    } catch (error) {
      if (error.status === 401) handleUnauthorized();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
