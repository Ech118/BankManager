import { DemoReport } from "@/components/DemoReport";

export default function Demo() {
  return (
    <>
      <h1 className="page-title">Full AI report example</h1>
      <p className="lede">Every part of the report an AI run produces, shown for a sample company. For real filings with no model involved, see Live SEC data.</p>
      <DemoReport />
    </>
  );
}
