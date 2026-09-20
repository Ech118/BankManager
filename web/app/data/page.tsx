import { SecData } from "@/components/SecData";

export const metadata = {
  title: "Live SEC data",
};

export default function DataPage() {
  return (
    <>
      <h1 className="page-title">Live SEC data</h1>
      <p className="lede">
        Real filings from SEC EDGAR, normalized by <code>data/</code> and computed by{" "}
        <code>calc/</code>. No model wrote any number on this page, and every figure links to the
        filing it came from.
      </p>
      <SecData />
    </>
  );
}
