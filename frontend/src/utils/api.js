export const API_BASE = '/api';

export const resolveImageUrl = (url) => {
  if (!url || typeof url !== 'string') return url;
  if (url.startsWith('/static/')) return url;
  if (url.startsWith('static/')) return `/${url}`;
  try {
    const parsed = new URL(url);
    if (
      (parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost') &&
      parsed.pathname.startsWith('/static/')
    ) {
      return parsed.pathname;
    }
  } catch {
    // Keep non-URL strings unchanged
  }
  return url;
};

const parseErrorMessage = async (res, fallbackMessage) => {
  try {
    const text = await res.text();
    if (!text) return fallbackMessage;
    try {
      const parsed = JSON.parse(text);
      return parsed.error || text;
    } catch {
      return text;
    }
  } catch {
    return fallbackMessage;
  }
};

export const fetchSettings = async () => {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res, `HTTP ${res.status}`));
  }
  return res.json();
};

export const saveSettings = async ({ engine, apiKey }) => {
  const res = await fetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ engine, apiKey }),
  });
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res, `HTTP ${res.status}`));
  }
  return res.json();
};

export const fetchHistory = async () => {
  const res = await fetch(`${API_BASE}/history`);
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res, `HTTP ${res.status}`));
  }
  const items = await res.json();
  if (!Array.isArray(items)) return [];
  return items.map((entry) => ({
    ...entry,
    name: typeof entry?.name === 'string' ? entry.name : '',
    images: Array.isArray(entry?.images)
      ? entry.images.map((img) => ({
          ...img,
          original: resolveImageUrl(img?.original),
          translated: resolveImageUrl(img?.translated),
        }))
      : [],
  }));
};

export const renameHistoryBatch = async (id, name) => {
  const res = await fetch(`${API_BASE}/history/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res, `HTTP ${res.status}`));
  }
  return res.json();
};

export const deleteHistoryBatch = async (id) => {
  const res = await fetch(`${API_BASE}/history/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res, `HTTP ${res.status}`));
  }
  return res.json();
};

export const clearAllHistory = async () => {
  const res = await fetch(`${API_BASE}/clear-history`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res, `HTTP ${res.status}`));
  }
  return res.json();
};

export const processImages = async (formData) => {
  const res = await fetch(`${API_BASE}/process-image`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    throw new Error(await parseErrorMessage(res, `HTTP ${res.status}`));
  }
  const data = await res.json();
  return {
    ...data,
    results: Array.isArray(data?.results)
      ? data.results.map((item) => ({
          ...item,
          original: resolveImageUrl(item?.original),
          translated: resolveImageUrl(item?.translated),
        }))
      : [],
  };
};
