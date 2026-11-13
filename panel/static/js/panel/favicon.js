const FAVICON_SIZE = 32;

let lastStatus = null;

export function beaconKindFromStatus(status) {
  if (!status || status.stale) return 'stale';
  if (status.overall === 'ok' || status.ok) return 'ok';
  if (status.overall === 'down') return 'alarm';
  return 'stale';
}

let probe;

function beaconComputed(kind) {
  if (!probe) {
    probe = document.createElement('div');
    probe.setAttribute('aria-hidden', 'true');
    probe.style.cssText =
      'position:fixed;left:-9999px;top:0;width:14px;height:14px;pointer-events:none;animation:none!important;filter:none!important';
    document.body.appendChild(probe);
  }
  const cls =
    kind === 'ok' ? 'ok' : kind === 'alarm' ? 'alarm' : 'stale';
  probe.className = `status-beacon status-beacon--${cls}`;
  probe.style.animation = 'none';
  return getComputedStyle(probe);
}

function parseColor(input) {
  const scratch = document.createElement('canvas');
  const ctx = scratch.getContext('2d');
  if (!ctx || !input) return 'rgba(0,0,0,0)';
  ctx.fillStyle = input;
  return ctx.fillStyle;
}

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function pxToken(name, fallback) {
  const n = parseFloat(token(name));
  return Number.isFinite(n) ? n : fallback;
}

function trianglePath(ctx, size) {
  const pad = size * 0.08;
  const width = size - pad * 2;
  const height = width * (Math.sqrt(3) / 2);
  const cx = size / 2;
  const top = (size - height) / 2;
  ctx.beginPath();
  ctx.moveTo(cx, top);
  ctx.lineTo(cx + width / 2, top + height);
  ctx.lineTo(cx - width / 2, top + height);
  ctx.closePath();
}

function fillTriangleWithGlow(ctx, size, core, glow, glowSoft) {
  if (glowSoft) {
    ctx.save();
    ctx.shadowColor = glowSoft;
    ctx.shadowBlur = pxToken('--space-4', 16) * 0.55;
    ctx.fillStyle = core;
    trianglePath(ctx, size);
    ctx.fill();
    ctx.restore();
  }
  if (glow) {
    ctx.save();
    ctx.shadowColor = glow;
    ctx.shadowBlur = pxToken('--space-2', 8) * 0.65;
    ctx.fillStyle = core;
    trianglePath(ctx, size);
    ctx.fill();
    ctx.restore();
  }
  ctx.fillStyle = core;
  trianglePath(ctx, size);
  ctx.fill();
}

function applySpecular(ctx, size) {
  const hx = size * 0.42;
  const hy = size * 0.34;
  const hi = ctx.createRadialGradient(hx, hy, 0, size / 2, size / 2, size * 0.45);
  hi.addColorStop(0, 'rgba(255,255,255,0.38)');
  hi.addColorStop(0.45, 'rgba(255,255,255,0)');
  ctx.save();
  ctx.globalCompositeOperation = 'source-atop';
  ctx.fillStyle = hi;
  ctx.fillRect(0, 0, size, size);
  ctx.restore();
}

function drawBeacon(ctx, size, kind) {
  ctx.clearRect(0, 0, size, size);

  if (kind === 'stale') {
    const cs = beaconComputed('stale');
    const core = parseColor(cs.backgroundColor || token('--beacon-stale-core'));
    const alpha = parseFloat(cs.opacity) || 0.35;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = core;
    trianglePath(ctx, size);
    ctx.fill();
    ctx.globalAlpha = 1;
    return;
  }

  if (kind === 'ok') {
    const core = parseColor(beaconComputed('ok').backgroundColor || token('--beacon-ok-core'));
    fillTriangleWithGlow(
      ctx,
      size,
      core,
      parseColor(token('--beacon-ok-glow')),
      parseColor(token('--beacon-ok-glow-soft')),
    );
    applySpecular(ctx, size);
    return;
  }

  if (kind === 'alarm') {
    const core = parseColor(beaconComputed('alarm').backgroundColor || token('--beacon-alarm-core'));
    ctx.save();
    ctx.shadowColor = parseColor(token('--beacon-alarm-halo'));
    ctx.shadowBlur = pxToken('--space-6', 32) * 0.45;
    ctx.fillStyle = core;
    trianglePath(ctx, size);
    ctx.fill();
    ctx.restore();
    fillTriangleWithGlow(ctx, size, core, parseColor(token('--beacon-alarm-glow')), '');
    applySpecular(ctx, size);
  }
}

let canvas;

function faviconCanvas() {
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.width = FAVICON_SIZE;
    canvas.height = FAVICON_SIZE;
  }
  return canvas;
}

function setFaviconHref(dataUrl) {
  let link = document.getElementById('status-favicon');
  if (!link) {
    link = document.createElement('link');
    link.id = 'status-favicon';
    link.rel = 'icon';
    link.type = 'image/png';
    link.sizes = '32x32';
    document.head.appendChild(link);
  }
  link.href = dataUrl;
}

export function updateStatusFavicon(status) {
  lastStatus = status;
  const kind = beaconKindFromStatus(status);
  const c = faviconCanvas();
  const ctx = c.getContext('2d');
  if (!ctx) return;
  drawBeacon(ctx, FAVICON_SIZE, kind);
  setFaviconHref(c.toDataURL('image/png'));
}

export function refreshStatusFavicon() {
  updateStatusFavicon(lastStatus);
}
