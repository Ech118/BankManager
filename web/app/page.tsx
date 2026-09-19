import { Analyzer } from "@/components/Analyzer";

export default function Home() {
  return (
    <>
      <h1 className="page-title">Will this stock beat the S&amp;P 500?</h1>
      <p className="lede">
        Enter a ticker. Agents read the filings, code does the math, a red team argues the other side, and every claim is
        checked against its source before you see it.
      </p>
      <Analyzer />
    </>
  );
}
