import { DemoReport } from "@/components/DemoReport";

export default function Demo() {
  return (
    <>
      <h1 className="page-title">ACME demo report</h1>
      <p className="lede">A fictional company, rendered from the frozen fixture. It exercises every part of the report.</p>
      <DemoReport />
    </>
  );
}
