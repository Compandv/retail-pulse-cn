import type { Metadata } from "next";
import latest from "../../public/data/longform/latest.json";
import { LongformDailyView } from "../LongformDailyView";
import type { LongformDaily } from "../longform-types";

export const metadata: Metadata = { title: "复盘长图｜散户温度计" };

export default function ReportPage() {
  return <LongformDailyView initial={latest as unknown as LongformDaily} />;
}
