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

  const state = {
    token: localStorage.getItem("infoflow_token") || "",
    user: null,
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
    searchTimer: null,
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
      throw new Error("Сессия истекла. Войдите снова.");
    }
    if (!response.ok) {
      let parsed = null;
      try {
        parsed = await response.json();
      } catch (_error) {
        }
      throw new Error(formatError(parsed, `Ошибка ${response.status}`));
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

  function showAuth() {
    $("#app-screen").classList.add("is-hidden");
    $("#auth-screen").classList.remove("is-hidden");
    $("#login-error").textContent = "";
    $("#register-error").textContent = "";
  }

  function showApp() {
    $("#auth-screen").classList.add("is-hidden");
    $("#app-screen").classList.remove("is-hidden");
    $("#user-email").textContent = state.user?.email || "";
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
    try {
      await api("/items", {
        method: "POST",
        body: {
          type: "link",
          url: String(data.get("url") || "").trim(),
          title: String(data.get("title") || "").trim() || null,
          tags: parseTags(String(data.get("tags") || "")),
        },
      });
      form.reset();
      toast("Сохранено. AI делает резюме и теги…", "success");
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
    try {
      await api("/items", {
        method: "POST",
        body: {
          type: "note",
          text: String(data.get("text") || "").trim(),
          title: String(data.get("title") || "").trim() || null,
          tags: parseTags(String(data.get("tags") || "")),
        },
      });
      form.reset();
      toast("Заметка сохранена. AI уже работает…", "success");
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
    data.append("file", input.files[0]);
    data.append("title", String(new FormData(form).get("title") || ""));
    data.append("tags", String(new FormData(form).get("tags") || ""));

    setBusy(button, true, "Загружаю…");
    try {
      await api("/items/upload", { method: "POST", body: data, form: true });
      form.reset();
      $("#dropzone-title").textContent = "Перетащите файл или нажмите";
      toast("Файл загружен. AI извлекает текст…", "success");
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

    $("#search-mode").addEventListener("change", (event) => {
      state.mode = event.target.value;
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
    bindEvents();
    if (!state.token) {
      showAuth();
      return;
    }
    try {
      state.user = await api("/auth/me");
      showApp();
    } catch (_error) {
      handleUnauthorized();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
