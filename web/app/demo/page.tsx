import { DemoReport } from "@/components/DemoReport";

export default function Demo() {
  return (
    <>
      <h1 className="page-title">Full AI report example</h1>
      <p className="lede">ACME, a FICTIONAL company, rendered from the frozen fixture: every part of the report an AI run produces. For real filings with no model involved, see Live SEC data.</p>
      <DemoReport />
    </>
  );
}
