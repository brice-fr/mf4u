<script lang="ts">
  /**
   * AboutDialog — modal showing app icon, name, version and copyright.
   *
   * Props
   *   open    – controls visibility
   *   onclose – called when the user dismisses the dialog
   */
  let {
    open = false,
    onclose = () => {},
  }: { open?: boolean; onclose?: () => void } = $props();

  const version   = import.meta.env.VITE_APP_VERSION ?? "0.1.0";
  const copyright = `© ${new Date().getFullYear()} Brice LECOLE`;

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget) onclose();
  }
  function handleKey(e: KeyboardEvent) {
    if (e.key === "Escape" || e.key === "Enter") onclose();
  }

  let okBtn: HTMLButtonElement | null = $state(null);
  $effect(() => { if (open) setTimeout(() => okBtn?.focus(), 40); });
</script>

{#if open}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="backdrop"
    role="dialog"
    aria-modal="true"
    aria-label="About mf4u"
    tabindex="-1"
    onclick={handleBackdrop}
    onkeydown={handleKey}
  >
    <div class="card">
      <!-- App icon -->
      <img class="app-icon" src="/icon.png" alt="mf4u icon" draggable="false" />

      <!-- App title -->
      <h1 class="app-title">
        <span class="title-mf4">mf4</span><span class="title-u">u</span>
      </h1>

      <!-- Subtitle -->
      <p class="app-subtitle">mf4 utility</p>

      <!-- Version -->
      <p class="app-version">Version {version}</p>

      <hr class="divider" />

      <!-- Copyright -->
      <p class="app-copyright">{copyright}</p>

      <button class="btn-ok" bind:this={okBtn} onclick={onclose}>OK</button>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    backdrop-filter: blur(4px);
  }

  .card {
    background: #1e1e1e;
    border: 1px solid #2e2e2e;
    border-radius: 14px;
    padding: 32px 40px 26px;
    width: 280px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.7);
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  .app-icon {
    width: 80px;
    height: 80px;
    border-radius: 18px;
    margin-bottom: 10px;
    user-select: none;
  }

  .app-title {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin: 0;
  }
  .title-mf4 { color: #dce6f5; }
  .title-u   { color: #6c9ef8; }

  .app-subtitle {
    font-size: 12px;
    color: #555;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin: 0;
  }

  .app-version {
    font-size: 12.5px;
    color: #666;
    margin: 4px 0 0;
  }

  .divider {
    width: 100%;
    border: none;
    border-top: 1px solid #2a2a2a;
    margin: 10px 0 6px;
  }

  .app-copyright {
    font-size: 11.5px;
    color: #444;
    text-align: center;
    margin: 0;
    line-height: 1.5;
  }

  .btn-ok {
    margin-top: 18px;
    padding: 6px 36px;
    background: #6c9ef8;
    color: #fff;
    border: none;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.12s;
  }
  .btn-ok:hover  { background: #7aabfa; }
  .btn-ok:active { background: #5588e0; }
</style>
