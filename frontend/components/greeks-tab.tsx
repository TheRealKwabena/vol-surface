"use client";

import { useMemo, useState } from "react";
import { LineChart, SlidersHorizontal } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { GreeksChart } from "@/components/greeks-chart";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import { bsmGreeks, bsmPrice, type OptionType } from "@/lib/bsm";
import { cn } from "@/lib/utils";

function SliderField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  format,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        <span className="text-sm font-medium text-primary tabular-nums">
          {format ? format(value) : value.toFixed(2)}
        </span>
      </div>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={(v) => {
          const next = (v as number[])[0];
          if (next !== undefined) onChange(next);
        }}
      />
    </div>
  );
}

function Metric({ label, value, signed }: { label: string; value: number; signed?: boolean }) {
  const formatted = Math.abs(value) < 0.001 ? value.toFixed(5) : value.toFixed(4);
  const tone = signed
    ? value > 1e-9
      ? "text-success"
      : value < -1e-9
        ? "text-destructive"
        : "text-foreground"
    : "text-foreground";
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border/60 bg-muted/30 px-3 py-2.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-lg font-semibold tabular-nums", tone)}>{formatted}</span>
    </div>
  );
}

export function GreeksTab() {
  const [S, setS] = useState(100);
  const [K, setK] = useState(100);
  const [T, setT] = useState(0.5);
  const [r, setR] = useState(0.04);
  const [q, setQ] = useState(0.015);
  const [sigma, setSigma] = useState(0.2);
  const [optionType, setOptionType] = useState<OptionType>("call");

  const price = useMemo(() => bsmPrice(S, K, T, r, q, sigma, optionType), [S, K, T, r, q, sigma, optionType]);
  const greeks = useMemo(() => bsmGreeks(S, K, T, r, q, sigma, optionType), [S, K, T, r, q, sigma, optionType]);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SlidersHorizontal className="size-4 text-primary" />
            Live Greeks Explorer
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Pure from-scratch BSM engine — no data fetch needed. Drag the sliders.
          </p>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div className="flex flex-col gap-5">
            <SliderField label="Spot price (S)" value={S} onChange={setS} min={10} max={1000} step={1} />
            <SliderField label="Strike (K)" value={K} onChange={setK} min={10} max={1000} step={1} />
            <SliderField
              label="Time to expiry, years (T)"
              value={T}
              onChange={setT}
              min={0.01}
              max={3}
              step={0.01}
            />
          </div>
          <div className="flex flex-col gap-5">
            <SliderField
              label="Risk-free rate (r)"
              value={r}
              onChange={setR}
              min={-0.02}
              max={0.1}
              step={0.001}
              format={(v) => v.toFixed(3)}
            />
            <SliderField
              label="Dividend yield (q)"
              value={q}
              onChange={setQ}
              min={0}
              max={0.1}
              step={0.001}
              format={(v) => v.toFixed(3)}
            />
            <SliderField label="Volatility (σ)" value={sigma} onChange={setSigma} min={0.01} max={2} step={0.01} />
          </div>
          <div className="md:col-span-2">
            <Label className="mb-2 block">Option type</Label>
            <RadioGroup
              value={optionType}
              onValueChange={(v) => setOptionType(v as OptionType)}
              className="flex flex-row gap-6"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="call" id="opt-call" />
                <Label htmlFor="opt-call">call</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="put" id="opt-put" />
                <Label htmlFor="opt-put">put</Label>
              </div>
            </RadioGroup>
          </div>
        </CardContent>
      </Card>

      <Card className="border-primary/25 bg-primary/[0.03]">
        <CardContent className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Theoretical price</span>
              <span className="text-4xl font-semibold tabular-nums">{price.toFixed(4)}</span>
            </div>
            <Badge variant={optionType === "call" ? "default" : "secondary"} className="uppercase">
              {optionType}
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Delta" value={greeks.delta} signed />
            <Metric label="Gamma" value={greeks.gamma} />
            <Metric label="Vega" value={greeks.vega} />
            <Metric label="Theta (per yr)" value={greeks.theta} signed />
            <Metric label="Rho" value={greeks.rho} signed />
            <Metric label="Vanna" value={greeks.vanna} signed />
            <Metric label="Volga" value={greeks.volga} signed />
            <Metric label="Charm" value={greeks.charm} signed />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <LineChart className="size-4 text-primary" />
            Gamma &amp; Vega vs. Spot Price
          </CardTitle>
        </CardHeader>
        <CardContent>
          <GreeksChart S={S} K={K} T={T} r={r} q={q} sigma={sigma} optionType={optionType} />
        </CardContent>
      </Card>
    </div>
  );
}
