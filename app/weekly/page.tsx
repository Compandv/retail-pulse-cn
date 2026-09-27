import type { Metadata } from "next";
import latest from "../../public/data/weekly/latest.json";
import { LongformWeeklyView } from "../LongformWeeklyView";
import type { LongformWeekly } from "../longform-types";

export const metadata: Metadata = { title: "周报｜散户温度计" };

export default function WeeklyPage() {
  return <LongformWeeklyView initial={latest as unknown as LongformWeekly} />;
}
