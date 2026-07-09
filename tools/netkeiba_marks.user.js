// ==UserScript==
// @name         Sonoda Keiba - netkeiba marks
// @namespace    sonoda-keiba-program
// @version      0.5.1
// @description  Apply T-10 prediction marks on nar.netkeiba shutuba (sonoda_marks query)
// @match        https://nar.netkeiba.com/race/shutuba.html*
// @match        https://nar.netkeiba.com/race/shutuba.html?*
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function () {
  "use strict";

  const SCRIPT_VERSION = "0.5.1";
  console.info("[sonoda-marks] userscript loaded v" + SCRIPT_VERSION, location.href);

  const MARK_LABEL = {
    1: "\u25ce",
    2: "\u25cb",
    3: "\u25b2",
    4: "\u25b3",
    5: "\u2606",
  };

  function parseMarks() {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get("sonoda_marks") || "";
    if (!raw) {
      const hash = (window.location.hash || "").replace(/^#/, "");
      const m = hash.match(/(?:^|&)marks=([^&]+)/) || hash.match(/^marks=(.+)$/);
      if (m) return parseRaw(m[1]);
      return [];
    }
    return parseRaw(raw);
  }

  function parseRaw(raw) {
    const out = [];
    for (const part of raw.split(",")) {
      const [uma, code] = part.trim().split(":");
      if (!uma || !code) continue;
      if (!/^\d+$/.test(uma) || !/^[1-5]$/.test(code)) continue;
      out.push({ uma, code });
    }
    return out;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitFor(fn, timeoutMs = 30000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        if (fn()) return true;
      } catch (_e) {}
      await sleep(200);
    }
    return false;
  }

  function getCookie(key) {
    const parts = (" " + document.cookie + ";").split(";");
    for (const part of parts) {
      const p = part.trim();
      const eq = p.indexOf("=");
      if (eq < 0) continue;
      if (p.substring(0, eq) === key) {
        return decodeURIComponent(p.substring(eq + 1));
      }
    }
    return "";
  }

  function showToast(msg, isError) {
    const el = document.createElement("div");
    el.textContent = msg;
    el.style.cssText =
      "position:fixed;top:12px;right:12px;z-index:99999;color:#fff;" +
      "padding:10px 14px;border-radius:8px;font:14px/1.4 sans-serif;" +
      "box-shadow:0 2px 8px rgba(0,0,0,.25);max-width:400px;white-space:pre-wrap;" +
      (isError ? "background:#b42318;" : "background:#1a7f37;");
    document.body.appendChild(el);
    setTimeout(() => el.remove(), isError ? 12000 : 7000);
  }

  function getMarkSelect(uma) {
    return document.querySelector(`#mark_${uma}`);
  }

  function getMarkRow(uma) {
    const sel = getMarkSelect(uma);
    return sel ? sel.closest("tr.HorseList") : null;
  }

  function allMarkDropdownsReady() {
    const selects = document.querySelectorAll('select[id^="mark_"]');
    if (!selects.length) return false;
    for (const sel of selects) {
      const tz = sel.nextElementSibling;
      if (!tz || !tz.classList.contains("tzSelect")) return false;
      const liCount = tz.querySelectorAll(".dropDown li").length;
      const optCount = sel.querySelectorAll("option").length;
      if (liCount < optCount) return false;
    }
    return true;
  }

  async function ensureMarkMode() {
    const mode = getCookie("mark_mode");
    if (!mode || mode === "mark") return true;
    showToast(
      "\u5370\u8868\u793a\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002\n\u51fa\u99ac\u8868\u306e\u300c\u5207\u66ff\u300d\u2192\u5370\u8868\u793a\u306b\u3057\u3066\u518d\u8a66\u884c\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
      true
    );
    return false;
  }

  async function waitForShutubaReady() {
    const ok = await waitFor(() => {
      return (
        typeof window.jQuery !== "undefined" &&
        typeof window.update_cart_checkbox === "function" &&
        typeof window._shutuba_cart_group === "string" &&
        window._shutuba_cart_group.length > 0 &&
        allMarkDropdownsReady()
      );
    }, 30000);
    if (!ok) return false;
    await sleep(1500);
    return true;
  }

  function findMarkLi(uma, code) {
    const clientData = `${uma}_${code}`;
    const sel = getMarkSelect(uma);
    if (!sel) return null;
    const tz = sel.nextElementSibling;
    if (!tz || !tz.classList.contains("tzSelect")) return null;
    const optIndex = Array.from(sel.options).findIndex((o) => o.value === clientData);
    if (optIndex < 0) return null;
    const lis = tz.querySelectorAll(".dropDown li");
    return lis[optIndex] || null;
  }

  /**
   * shutuba.js \u304c li \u306b\u7d10\u3065\u3051\u305f\u30cf\u30f3\u30c9\u30e9\u3092\u672c\u7269\u306e\u30af\u30ea\u30c3\u30af\u3067\u8d77\u52d5\u3059\u308b\u3002
   * DOM \u3092\u76f4\u63a5\u66f8\u304d\u63db\u3048\u308b\u3060\u3051\u3067\u306f tr \u306e Selected \u3068\u5408\u308f\u306a\u3044\u3053\u3068\u304c\u3042\u308b\u3002
   */
  function clickMarkLi(uma, code) {
    const li = findMarkLi(uma, code);
    if (!li) return { ok: false, reason: "li missing" };
    li.click();
    return { ok: true };
  }

  /** shutuba.js li.click \u3068\u540c\u3058\u51e6\u7406\u306e\u30d5\u30a9\u30fc\u30eb\u30d0\u30c3\u30af */
  function applyMarkDirect(uma, code) {
    const clientData = `${uma}_${code}`;
    const $ = window.jQuery;
    if (!$) return { ok: false, reason: "jQuery missing" };

    const $sel = $(`#mark_${uma}`);
    if (!$sel.length) return { ok: false, reason: `mark_${uma} missing` };

    const $opt = $sel.find(`option[value="${clientData}"]`);
    if (!$opt.length) return { ok: false, reason: `option ${clientData}` };

    const $tz = $sel.next(".tzSelect");
    if (!$tz.length) return { ok: false, reason: "tzSelect missing" };

    const $row = $tz.closest("tr.HorseList");
    const markCode = String(code);

    $tz.find(".selectBox").html($opt.text());
    $tz.find(".dropDown").trigger("hide");
    $sel.val(clientData);

    if (markCode === "99") {
      $row.addClass("NoSelected").removeClass("Selected");
    } else if (markCode !== "0") {
      $row.removeClass("NoSelected").addClass("Selected");
    } else {
      $row.removeClass("Selected NoSelected");
    }

    if (typeof window.update_cart_checkbox !== "function" || !window._shutuba_cart_group) {
      return { ok: false, reason: "cart api missing" };
    }
    window.update_cart_checkbox(
      window._shutuba_cart_group,
      String(uma),
      clientData,
      "add"
    );
    return { ok: true };
  }

  function isMarkApplied(uma, code) {
    const clientData = `${uma}_${code}`;
    const sel = getMarkSelect(uma);
    if (!sel) return false;

    const valOk = String(sel.value) === clientData;
    const tz = sel.nextElementSibling;
    const box = tz && tz.classList.contains("tzSelect")
      ? tz.querySelector(".selectBox")?.textContent.trim()
      : "";
    const opt = sel.querySelector(`option[value="${clientData}"]`);
    const boxOk = opt ? box === opt.textContent.trim() : false;
    return valOk || boxOk;
  }

  async function applyOneMark(uma, code) {
    let res = clickMarkLi(uma, code);
    await sleep(350);
    if (!isMarkApplied(uma, code)) {
      res = applyMarkDirect(uma, code);
      await sleep(350);
    }
    if (!isMarkApplied(uma, code)) {
      const li = findMarkLi(uma, code);
      if (li) {
        const tz = getMarkSelect(uma)?.nextElementSibling;
        tz?.querySelector(".selectBox")?.click();
        await sleep(60);
        li.click();
        await sleep(350);
      }
    }
    return isMarkApplied(uma, code);
  }

  async function applyAllMarks(marks) {
    const failed = [];
    for (const { uma, code } of marks) {
      const ok = await applyOneMark(uma, code);
      if (!ok) {
        const sel = getMarkSelect(uma);
        const row = getMarkRow(uma);
        failed.push(
          `${uma}\u756a(val=${sel?.value || "?"}, row=${row?.className || "?"})`
        );
      }
      await sleep(250);
    }
    return failed;
  }

  async function run() {
    const marks = parseMarks();
    if (!marks.length) {
      console.info(
        "[sonoda-marks] no sonoda_marks in URL (script is running, param missing)"
      );
      return;
    }

    console.info("[sonoda-marks] start", marks, location.href);
    showToast("Sonoda: \u5370\u3092\u9069\u7528\u4e2d\u2026");

    if (!(await ensureMarkMode())) return;

    const ready = await waitForShutubaReady();
    if (!ready) {
      showToast(
        "\u51fa\u99ac\u8868\u306e\u6e96\u5099\u304c\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002\n\u30da\u30fc\u30b8\u3092\u518d\u8aad\u8fbc\u307f\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        true
      );
      return;
    }

    let failed = await applyAllMarks(marks);

    // cart_get_itemlist \u2192 init_select_menu \u304c\u9045\u308c\u3066 tzSelect \u3092\u4f5c\u308a\u76f4\u3059\u5834\u5408\u306e\u518d\u8a66\u884c
    if (failed.length) {
      await sleep(2500);
      failed = await applyAllMarks(marks);
    }

    if (failed.length) {
      const msg =
        "\u4e00\u90e8\u5931\u6557:\n" +
        failed.join("\n") +
        "\n\n\u203bnetkeiba\u30ed\u30b0\u30a4\u30f3\u78ba\u8a8d\u3001Console\u306b [sonoda-marks] \u3092\u78ba\u8a8d";
      showToast(msg, true);
      console.warn("[sonoda-marks] failed", failed);
      return;
    }

    const labels = marks
      .map((m) => `${m.uma}\u756a${MARK_LABEL[m.code] || m.code}`)
      .join(" ");
    showToast(`\u5370\u3092\u8a2d\u5b9a\u3057\u307e\u3057\u305f\n${labels}`);
    console.info("[sonoda-marks] applied", marks);
  }

  function start() {
    if (!document.body) {
      window.addEventListener("DOMContentLoaded", () => run(), { once: true });
      return;
    }
    run();
  }

  if (document.readyState === "complete") {
    start();
  } else {
    window.addEventListener("load", () => start(), { once: true });
  }
})();
