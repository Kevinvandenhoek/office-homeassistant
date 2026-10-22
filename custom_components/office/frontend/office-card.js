// The Office card: the colleagues' skip days as a banner, and a button per office day for your own.
// Loaded on every page by the integration; add it to a dashboard as `type: custom:office-card`.

const DEFAULT_ENTITY = "sensor.office_skip_days";

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
// Names come from the host: never as HTML.
const esc = (text) => String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

class OfficeCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: DEFAULT_ENTITY, ...config };
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    // Only draw again when the sensor changed, so a tap is not lost in a redraw for another entity.
    const key = state ? `${state.state}|${state.last_updated}` : "none";
    if (key === this._key) return;
    this._key = key;
    this._render(state);
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig() {
    return { entity: DEFAULT_ENTITY };
  }

  _render(state) {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const days = state?.attributes?.days ?? [];
    const unavailable = !state || state.state === "unavailable" || state.state === "unknown";
    const banner = [];
    for (const day of days) {
      for (const name of day.skipping) banner.push({ name, when: day.name, today: day.name === "today" });
    }
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        h2 { margin: 0 0 12px; font-size: 16px; font-weight: 500; }
        .banner { border-radius: 12px; padding: 10px 12px; margin-bottom: 12px; font-size: 14px;
          background: color-mix(in srgb, var(--warning-color, #ffa600) 16%, transparent); }
        .banner.today { background: color-mix(in srgb, var(--error-color, #db4437) 18%, transparent); font-weight: 500; }
        .quiet { color: var(--secondary-text-color); font-size: 14px; margin-bottom: 12px; }
        .day { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid var(--divider-color); }
        .day:first-of-type { border-top: 0; }
        .text { flex: 1; min-width: 0; }
        .name { font-size: 14px; }
        .who { font-size: 12px; color: var(--secondary-text-color); }
        button { font: inherit; font-size: 13px; border: 0; border-radius: 16px; padding: 6px 12px; cursor: pointer;
          background: var(--secondary-background-color); color: var(--primary-text-color); }
        button.on { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
      </style>
      <ha-card>
        <h2>${esc(this._config.title ?? "Office")}</h2>
        ${unavailable ? `<div class="quiet">Can't reach the office. The skip days come back when the host is reachable.</div>` : ""}
        ${!unavailable && !banner.length ? `<div class="quiet">Everyone comes to the office this week and next.</div>` : ""}
        ${banner.map((b) => `<div class="banner ${b.today ? "today" : ""}">${esc(b.name)} skips ${esc(b.when)}.</div>`).join("")}
        ${unavailable ? "" : days.map((day, i) => `
          <div class="day">
            <div class="text">
              <div class="name">${esc(capitalize(day.name))}</div>
              <div class="who">${esc(this._line(day))}</div>
            </div>
            <button data-i="${i}" class="${day.mine ? "on" : ""}">${day.mine ? "Skipping" : "Skip"}</button>
          </div>`).join("")}
      </ha-card>`;
    this.shadowRoot.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        const day = days[Number(button.dataset.i)];
        this._hass.callService("office", "set_skip_day", { date: day.date, skip: !day.mine });
      });
    });
  }

  _line(day) {
    const parts = [];
    if (day.mine) parts.push("You skip");
    if (day.skipping.length) parts.push(`${day.skipping.join(", ")} skip${day.skipping.length === 1 ? "s" : ""}`);
    if (day.pending_until) parts.push("the others see your change in a minute");
    return parts.join(" · ") || "Everyone in";
  }
}

if (!customElements.get("office-card")) {
  customElements.define("office-card", OfficeCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: "office-card", name: "Office", description: "Skip days of you and your colleagues." });
}
