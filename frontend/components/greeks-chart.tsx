"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import { bsmGreeks, type OptionType } from "@/lib/bsm";

// plotly.js touches `window` at import time -- must be client-only, no SSR.
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const AXIS_COLOR = "#71717a";

interface GreeksChartProps {
  S: number;
  K: number;
  T: number;
  r: number;
  q: number;
  sigma: number;
  optionType: OptionType;
}

export function GreeksChart({ S, K, T, r, q, sigma, optionType }: GreeksChartProps) {
  const { sGrid, gammas, vegas } = useMemo(() => {
    const lo = Math.max(S * 0.5, 1);
    const hi = S * 1.5;
    const n = 200;
    const sGrid: number[] = [];
    const gammas: number[] = [];
    const vegas: number[] = [];
    for (let i = 0; i < n; i++) {
      const s = lo + ((hi - lo) * i) / (n - 1);
      const g = bsmGreeks(s, K, T, r, q, sigma, optionType);
      sGrid.push(s);
      gammas.push(g.gamma);
      vegas.push(g.vega);
    }
    return { sGrid, gammas, vegas };
  }, [S, K, T, r, q, sigma, optionType]);

  return (
    <Plot
      data={[
        { x: sGrid, y: gammas, name: "Gamma", type: "scatter", mode: "lines", yaxis: "y1" },
        { x: sGrid, y: vegas, name: "Vega", type: "scatter", mode: "lines", yaxis: "y2" },
      ]}
      layout={{
        xaxis: {
          title: { text: "Spot price" },
          color: AXIS_COLOR,
          gridcolor: "rgba(128,128,128,0.2)",
          exponentformat: "none",
        },
        yaxis: { title: { text: "Gamma" }, color: AXIS_COLOR, gridcolor: "rgba(128,128,128,0.2)" },
        yaxis2: { title: { text: "Vega" }, overlaying: "y", side: "right", color: AXIS_COLOR },
        shapes: [{ type: "line", x0: S, x1: S, y0: 0, y1: 1, yref: "paper", line: { dash: "dot", color: AXIS_COLOR } }],
        annotations: [{ x: S, y: 1, yref: "paper", showarrow: false, text: "current S", yanchor: "bottom", font: { color: AXIS_COLOR } }],
        height: 400,
        margin: { t: 20, l: 55, r: 55, b: 40 },
        legend: { orientation: "h", font: { color: AXIS_COLOR } },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: AXIS_COLOR },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "400px" }}
      useResizeHandler
    />
  );
}
