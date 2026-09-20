import { Analyzer } from "@/components/Analyzer";

export default function Home() {
  return (
    <>
      <section className="hero">
        <h1 className="page-title">
          Will this stock <span className="gradient-text">beat the S&amp;P&nbsp;500?</span>
        </h1>
        <p className="lede">
          Enter a ticker. Agents read the filings, code does the math, a red team argues the other side, and every claim is
          checked against its source before you see it.
        </p>
      </section>
      <Analyzer />
    </>
  );
}
