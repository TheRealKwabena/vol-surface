"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { SurfacePoint } from "@/lib/types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const AXIS_COLOR = "#71717a";

export function SurfacePlot({ points }: { points: SurfacePoint[] }) {
  const { x, y, z, iv, text } = useMemo(() => {
    const x = points.map((p) => p.log_moneyness);
    const y = points.map((p) => p.T);
    const z = points.map((p) => p.total_variance);
    const iv = points.map((p) => p.iv);
    const text = points.map((p) => `K=${p.strike.toFixed(1)}<br>T=${p.T.toFixed(3)}<br>IV=${p.iv.toFixed(3)}`);
    return { x, y, z, iv, text };
  }, [points]);

  return (
    <Plot
      data={[
        {
          x,
          y,
          z,
          mode: "markers",
          type: "scatter3d",
          marker: { size: 3, color: iv, colorscale: "Viridis", colorbar: { title: { text: "IV" } } },
          text,
          hoverinfo: "text",
        },
      ]}
      layout={{
        scene: {
          xaxis: { title: { text: "log-moneyness ln(K/F)" }, color: AXIS_COLOR },
          yaxis: { title: { text: "T (years)" }, color: AXIS_COLOR },
          zaxis: { title: { text: "total variance (σ²T)" }, color: AXIS_COLOR },
        },
        height: 650,
        margin: { l: 0, r: 0, t: 20, b: 0 },
        paper_bgcolor: "rgba(0,0,0,0)",
        font: { color: AXIS_COLOR },
      }}
      config={{ responsive: true }}
      style={{ width: "100%", height: "650px" }}
      useResizeHandler
    />
  );
}
