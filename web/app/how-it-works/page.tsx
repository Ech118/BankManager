import { FlowChart } from "@/components/FlowChart";

export const metadata = {
  title: "How it works",
};

export default function HowItWorks() {
  return (
    <>
      <h1 className="page-title">How it works</h1>
      <p className="lede">
        A team of AI agents reads the evidence, plain code does all the math, a red team argues the other side, and a verifier
        checks every claim before you see it.
      </p>
      <FlowChart />
    </>
  );
}
