// SSE consumer over fetch (we can't use EventSource because we need
// the Authorization header for JWT auth on /api/v1/chat/...).

export async function readSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const dataLines = block
        .split('\n')
        .filter(l => l.startsWith('data: '))
        .map(l => l.slice(6));
      if (!dataLines.length) continue;
      const dataStr = dataLines.join('\n');
      try {
        onEvent(JSON.parse(dataStr));
      } catch {
        // ignore parse errors
      }
    }
  }
}
