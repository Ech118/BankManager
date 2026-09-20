"use client";

import { useEffect, useState } from "react";

/** The shape `backtest/demo_data.py` writes. Loose on purpose: extra keys are fine. */
type Cell = {
  value: number | null;
  unit?: string | null;
  status?: string;
  reason?: string | null;
  not_applicable?: boolean;
  basis?: string | null;
  source?: { accession?: string | null; url?: string | null } | null;
};

type Row = { key: string; label: string; cells: Record<string, Cell> };

type Company = {
  ticker: string;
  company_name: string;
  as_of: string;
  scope_level?: string;
  data_quality?: { overall?: string; gaps?: string[] };
  latest_annual_period: string;
  market: Record<string, Cell & { as_of?: string }> & { as_of?: string };
  financials: {
    periods: string[];
    filed: Record<string, string>;
    form: Record<string, string>;
    accession: Record<string, string>;
    rows: Row[];
  };
  ttm?: Record<string, Cell> | null;
  metrics: {
    margins: Record<string, Record<string, Cell>>;
    growth: Record<string, Record<string, Cell>>;
    cagr: Record<string, Cell | number | string | null>;
    cash_flow: Record<string, Cell>;
    balance_sheet: Record<string, Cell>;
    per_share: Record<string, Cell>;
    returns: Record<string, Cell>;
    quality_flags: { flag: string; detail: string; severity: string }[];
  };
  valuation: {
    primary_multiple: string;
    basis?: { earnings_basis?: string; earnings_period?: string; note?: string };
    multiples: (Cell & { key: string; label: string })[];
    methods_skipped?: Record<string, string>;
    dcf?: {
      value_per_share: Cell;
      upside_to_price: Cell;
      assumptions?: Record<string, unknown>;
    };
  };
  peers: {
    median: Record<string, Cell & { usable_peers?: number; peer_count?: number }>;
    premium: Record<string, Cell>;
    rows: {
      ticker: string;
      market_cap: number | null;
      selection_reason?: string;
      multiples: Record<string, number | null>;
    }[];
  };
  reverse_dcf: {
    implied_fcf_cagr: Cell;
    implied_fcf_cagr_smoothed_base?: Cell;
    assumptions: { discount_rate: number; terminal_growth: number; horizon_years: number };
  };
  notes?: string[];
};

type Index = { tickers: string[]; rows: { ticker: string; company_name: string }[] };

const USD = (v: number | null | undefined) => {
  if (v === null || v === undefined) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(2)}`;
};

function show(cell: Cell | undefined): string {
  if (!cell || cell.value === null || cell.value === undefined) {
    return cell?.not_applicable ? "n/a" : "—";
  }
  const v = cell.value;
  switch (cell.unit) {
    case "fraction":
      return `${(v * 100).toFixed(1)}%`;
    case "multiple":
    case "ratio":
      return `${v.toFixed(2)}x`;
    case "usd_per_share":
      return `$${v.toFixed(2)}`;
    case "shares":
      return `${(v / 1e6).toFixed(0)}M`;
    case "days":
      return `${v.toFixed(1)}d`;
    default:
      return USD(v);
  }
}

/** A number with a link to the filing behind it. */
function Sourced({ cell }: { cell: Cell | undefined }) {
  const text = show(cell);
  const url = cell?.source?.url;
  const title = cell?.reason ?? cell?.source?.accession ?? undefined;
  if (!url) {
    return <span title={title ?? undefined}>{text}</span>;
  }
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" title={cell?.source?.accession ?? "SEC filing"}>
      {text}
    </a>
  );
}

export function SecData() {
  const [index, setIndex] = useState<Index | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/demo/data/index.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("no data bundle"))))
      .then((body: Index) => {
        setIndex(body);
        if (body.tickers?.length) void load(body.tickers[0]);
      })
      .catch(() => setError("No SEC data bundle in this build."));
  }, []);

  async function load(ticker: string) {
    setError(null);
    try {
      const res = await fetch(`/demo/data/${ticker}.json`, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      setCompany((await res.json()) as Company);
    } catch {
      setError(`Could not load ${ticker}.`);
    }
  }

  if (error) return <div className="banner banner-degraded">{error}</div>;
  if (!index || !company) return <p className="lede">Loading…</p>;

  const periods = company.financials.periods;
  const annual = company.latest_annual_period;
  const gaps = company.data_quality?.gaps ?? [];

  return (
    <div>
      <p className="lede">
        {index.tickers.map((t) => (
          <button
            key={t}
            type="button"
            className="ticker-chip"
            onClick={() => void load(t)}
            aria-current={t === company.ticker}
          >
            {t}
          </button>
        ))}
      </p>

      <section className="card">
        <h2>
          {company.company_name} ({company.ticker})
        </h2>
        <p className="lede">
          As of {company.as_of} · scope {company.scope_level ?? "supported"} · data quality{" "}
          {company.data_quality?.overall ?? "ok"}
        </p>
        <dl className="kv">
          <div>
            <dt>Price</dt>
            <dd>
              <Sourced cell={company.market.price} />
            </dd>
          </div>
          <div>
            <dt>Market cap</dt>
            <dd>
              <Sourced cell={company.market.market_cap} />
            </dd>
          </div>
          <div>
            <dt>Enterprise value</dt>
            <dd>
              <Sourced cell={company.market.enterprise_value} />
            </dd>
          </div>
          <div>
            <dt>Shares out</dt>
            <dd>
              <Sourced cell={company.market.shares_outstanding} />
            </dd>
          </div>
        </dl>
      </section>

      <section className="card">
        <h2>Financials</h2>
        <p className="lede">
          Every figure links to the filing it was read from. TTM:{" "}
          {company.ttm ? "published by data/" : "not published for this filer yet"}.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Line item</th>
                {periods.map((p) => (
                  <th key={p}>
                    {p}
                    <span className="sub">{company.financials.form[p]}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {company.financials.rows.map((row) => (
                <tr key={row.key}>
                  <th scope="row">{row.label}</th>
                  {periods.map((p) => (
                    <td key={p}>
                      <Sourced cell={row.cells[p]} />
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="computed">
                <th scope="row">Net margin (calc)</th>
                {periods.map((p) => (
                  <td key={p}>{show(company.metrics.margins[p]?.net)}</td>
                ))}
              </tr>
              <tr className="computed">
                <th scope="row">FCF margin (calc)</th>
                {periods.map((p) => (
                  <td key={p}>{show(company.metrics.margins[p]?.fcf)}</td>
                ))}
              </tr>
              <tr className="computed">
                <th scope="row">Revenue growth (calc)</th>
                {periods.map((p) => (
                  <td key={p}>{show(company.metrics.growth[p]?.revenue_yoy)}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <p className="sub">
          Filed: {periods.map((p) => `${p} ${company.financials.filed[p]}`).join(" · ")}
        </p>
      </section>

      <section className="card">
        <h2>Valuation</h2>
        <p className="lede">
          Primary multiple for this filer: <strong>{company.valuation.primary_multiple}</strong> ·
          divides {company.valuation.basis?.earnings_period ?? annual} (
          {company.valuation.basis?.earnings_basis ?? "latest_full_year"})
        </p>
        <dl className="kv">
          {company.valuation.multiples.map((m) => (
            <div key={m.key}>
              <dt>{m.label}</dt>
              <dd title={m.reason ?? undefined}>{show(m)}</dd>
            </div>
          ))}
          <div>
            <dt>FCF yield</dt>
            <dd>{show(company.metrics.cash_flow.fcf_yield)}</dd>
          </div>
          <div>
            <dt>ROE</dt>
            <dd>{show(company.metrics.returns.roe)}</dd>
          </div>
          <div>
            <dt>Book value / share</dt>
            <dd>{show(company.metrics.per_share.book_value_per_share)}</dd>
          </div>
          <div>
            <dt>Net debt</dt>
            <dd>{show(company.metrics.balance_sheet.net_debt)}</dd>
          </div>
        </dl>
        <h3>Reverse DCF</h3>
        <p>
          Today&rsquo;s price implies{" "}
          <strong>{show(company.reverse_dcf.implied_fcf_cagr)}</strong> FCF growth for{" "}
          {company.reverse_dcf.assumptions.horizon_years} years, at a{" "}
          {(company.reverse_dcf.assumptions.discount_rate * 100).toFixed(0)}% discount rate and{" "}
          {(company.reverse_dcf.assumptions.terminal_growth * 100).toFixed(0)}% terminal growth
          (both nominal).
          {company.reverse_dcf.implied_fcf_cagr_smoothed_base?.value != null && (
            <>
              {" "}
              On a three-year average FCF base:{" "}
              <strong>{show(company.reverse_dcf.implied_fcf_cagr_smoothed_base)}</strong>.
            </>
          )}
        </p>
        {company.valuation.dcf?.value_per_share?.value != null && (
          <p>
            Forward DCF fair value{" "}
            <strong>{show(company.valuation.dcf.value_per_share)}</strong> ({" "}
            {show(company.valuation.dcf.upside_to_price)} against the price).
          </p>
        )}
      </section>

      <section className="card">
        <h2>Peers</h2>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Peer</th>
                <th>Market cap</th>
                <th>P/E</th>
                <th>P/S</th>
                <th>EV/EBITDA</th>
                <th>Why this peer</th>
              </tr>
            </thead>
            <tbody>
              {company.peers.rows.map((peer) => (
                <tr key={peer.ticker}>
                  <th scope="row">{peer.ticker}</th>
                  <td>{USD(peer.market_cap)}</td>
                  <td>{peer.multiples.pe?.toFixed(1) ?? "—"}</td>
                  <td>{peer.multiples.p_s?.toFixed(1) ?? "—"}</td>
                  <td>{peer.multiples.ev_ebitda?.toFixed(1) ?? "—"}</td>
                  <td className="sub">{peer.selection_reason ?? ""}</td>
                </tr>
              ))}
              <tr className="computed">
                <th scope="row">Median</th>
                <td>—</td>
                <td>{show(company.peers.median.pe)}</td>
                <td>{show(company.peers.median.p_s)}</td>
                <td>{show(company.peers.median.ev_ebitda)}</td>
                <td className="sub">
                  {company.peers.median.pe?.usable_peers ?? 0} of{" "}
                  {company.peers.median.pe?.peer_count ?? company.peers.rows.length} peers carry a
                  P/E
                </td>
              </tr>
              <tr className="computed">
                <th scope="row">Premium to median</th>
                <td>—</td>
                <td>{show(company.peers.premium.pe)}</td>
                <td>{show(company.peers.premium.p_s)}</td>
                <td>{show(company.peers.premium.ev_ebitda)}</td>
                <td className="sub">{company.peers.premium.pe?.reason ?? ""}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {(gaps.length > 0 || company.metrics.quality_flags.length > 0) && (
        <section className="card">
          <h2>Data quality</h2>
          {company.metrics.quality_flags.map((flag) => (
            <p key={flag.flag}>
              <strong>{flag.flag}</strong> ({flag.severity}): {flag.detail}
            </p>
          ))}
          <ul>
            {gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
