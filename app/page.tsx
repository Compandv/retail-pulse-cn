import snapshot from "../public/data/latest.json";
import { MeasurementDashboard } from "./MeasurementDashboard";
import market from "../public/data/market/latest.json";
import type { MarketSnapshot } from "./market-types";
import report from "../public/data/report/latest.json";

export default function Home() {
  return <MeasurementDashboard initialSnapshot={snapshot} initialMarket={market as unknown as MarketSnapshot} initialReport={report} />;
}
