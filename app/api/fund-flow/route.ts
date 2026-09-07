import { collectLiveFlows, type FlowSource, type FlowKind, type LiveFlowSnapshot } from "../../../lib/fund-flow";

const cache = new Map<string, { value: LiveFlowSnapshot; checked: number; error?: string }>();
const pending = new Map<string, Promise<LiveFlowSnapshot>>();
export async function GET(request: Request) {
  const query = new URL(request.url).searchParams, source = query.get("source") || "eastmoney", kind = query.get("kind") || "industry";
  if (!["eastmoney", "ths"].includes(source) || !["industry", "concept"].includes(kind)) return Response.json({ error: "请选择有效来源与板块类型" }, { status: 400 });
  const key = `${source}:${kind}`, now = Date.now(), saved = cache.get(key);
  if (saved && now - saved.checked < 120000) return Response.json({ ...saved.value, stale: Boolean(saved.error), errors: saved.error ? [...saved.value.errors, saved.error] : saved.value.errors }, { headers: { "Cache-Control": "no-store" } });
  try {
    let job = pending.get(key);
    if (!job) {
      job = collectLiveFlows(source as FlowSource, kind as FlowKind).finally(() => pending.delete(key));
      pending.set(key, job);
    }
    const value = await job;
    if (saved?.value.complete && !value.complete) {
      cache.set(key, { ...saved, checked: now, error: "本次分页不完整，保留同来源上次完整结果" });
      return Response.json({ ...saved.value, stale: true, errors: [...value.errors, "本次分页不完整，保留同来源上次完整结果"] }, { headers: { "Cache-Control": "no-store" } });
    }
    cache.set(key, { value, checked: now });
    return Response.json(value, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "资金来源暂不可用";
    if (saved) {
      cache.set(key, { ...saved, checked: now, error: message });
      return Response.json({ ...saved.value, stale: true, errors: [...saved.value.errors, message] }, { headers: { "Cache-Control": "no-store" } });
    }
    return Response.json({ error: message, source, kind }, { status: 502, headers: { "Cache-Control": "no-store" } });
  }
}
