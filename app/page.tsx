import snapshot from "../public/data/latest.json";
import { Dashboard } from "./Dashboard";

export default function Home() {
  return <Dashboard initialSnapshot={snapshot} />;
}
