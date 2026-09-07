import { collectBoardMembers } from "../../../lib/market-members";
import { validSession } from "../../../lib/observations";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const code = params.get("code") || "", date = params.get("date") || "";
  if (!/^BK\d{4,6}$/.test(code) || !validSession(date)) return Response.json({ error: "请选择有效板块和已收盘交易日" }, { status: 400 });
  try { return Response.json(await collectBoardMembers(code, date), { headers: { "Cache-Control": "no-store" } }); }
  catch (error) { return Response.json({ error: error instanceof Error ? error.message : "板块成分暂不可用" }, { status: 502 }); }
}
