"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Filter,
  Info,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { SurfacePlot } from "@/components/surface-plot";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetchVolSurface } from "@/lib/api";

function Stat({
  label,
  value,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone?: "default" | "success";
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3">
        <div
          className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${
            tone === "success" ? "bg-success/10 text-success" : "bg-primary/10 text-primary"
          }`}
        >
          <Icon className="size-4" />
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-muted-foreground">{label}</span>
          <span className="text-2xl font-semibold tabular-nums">{value}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function VolSurfaceTab() {
  const [ticker, setTicker] = useState("SPY");
  const [maxExpiries, setMaxExpiries] = useState(8);
  const [maxSpreadFrac, setMaxSpreadFrac] = useState(0.4);
  const [requireVolOi, setRequireVolOi] = useState(true);

  const mutation = useMutation({
    mutationFn: () =>
      fetchVolSurface({
        ticker,
        max_expiries: maxExpiries,
        max_spread_frac: maxSpreadFrac,
        require_volume_or_oi: requireVolOi,
      }),
  });

  const result = mutation.data;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" />
            Implied Volatility Surface
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Forward and discount factor are implied per-expiry from put-call parity (no dividend-yield or
            risk-free-rate guess). IV is solved via Newton-Raphson with a Brent&apos;s-method fallback for
            non-convergent cases.
          </p>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="ticker">Ticker</Label>
              <Input id="ticker" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label>Max expiries to fetch</Label>
                <span className="text-sm font-medium text-primary">{maxExpiries}</span>
              </div>
              <Slider
                value={[maxExpiries]}
                min={1}
                max={20}
                step={1}
                onValueChange={(v) => {
                  const next = (v as number[])[0];
                  if (next !== undefined) setMaxExpiries(next);
                }}
              />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label>Max bid-ask spread (% of mid)</Label>
                <span className="text-sm font-medium text-primary">{Math.round(maxSpreadFrac * 100)}</span>
              </div>
              <Slider
                value={[Math.round(maxSpreadFrac * 100)]}
                min={5}
                max={100}
                step={1}
                onValueChange={(v) => {
                  const next = (v as number[])[0];
                  if (next !== undefined) setMaxSpreadFrac(next / 100);
                }}
              />
            </div>
            <div className="flex items-center gap-2 self-end pb-2">
              <Switch id="require-vol-oi" checked={requireVolOi} onCheckedChange={(c) => setRequireVolOi(c)} />
              <Label htmlFor="require-vol-oi">Require volume or open interest &gt; 0</Label>
            </div>
          </div>
          <div>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? "Fetching..." : "Fetch & Build Surface"}
            </Button>
          </div>

          {!result && !mutation.isPending && !mutation.isError && (
            <Alert>
              <Info className="size-4 text-primary" />
              <AlertTitle>Set your parameters and click Fetch &amp; Build Surface</AlertTitle>
              <AlertDescription>
                Note: SPY/SPX are American/European-settlement-flavored index-linked products; SPY itself is
                American-style but highly liquid and dividend-adjusted forwards from parity absorb most of that
                effect for near-the-money strikes.
              </AlertDescription>
            </Alert>
          )}

          {mutation.isError && (
            <Alert variant="destructive">
              <AlertTriangle className="size-4" />
              <AlertTitle>Pipeline failed</AlertTitle>
              <AlertDescription>{(mutation.error as Error).message}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {result && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Raw quotes" value={result.cleaning_report.rows_in} icon={Database} />
            <Stat label="After cleaning" value={result.cleaning_report.rows_out} icon={Filter} />
            <Stat label="Dropped" value={result.cleaning_report.rows_dropped} icon={Trash2} />
            <Stat
              label="IV solve convergence"
              value={`${result.convergence_rate.toFixed(1)}%`}
              icon={CheckCircle2}
              tone="success"
            />
          </div>

          <Accordion type="multiple">
            <AccordionItem value="cleaning">
              <AccordionTrigger>Cleaning filter breakdown</AccordionTrigger>
              <AccordionContent>
                <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                  {JSON.stringify(result.cleaning_report.filters, null, 2)}
                </pre>
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="forward">
              <AccordionTrigger>Forward / discount factor fit per expiry</AccordionTrigger>
              <AccordionContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Expiry</TableHead>
                        <TableHead>T</TableHead>
                        <TableHead>Forward</TableHead>
                        <TableHead>Discount factor</TableHead>
                        <TableHead>Implied rate</TableHead>
                        <TableHead>N points</TableHead>
                        <TableHead>R²</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.forward_fits.map((f) => (
                        <TableRow key={f.expiry}>
                          <TableCell>{f.expiry}</TableCell>
                          <TableCell>{f.T.toFixed(4)}</TableCell>
                          <TableCell>{f.forward.toFixed(2)}</TableCell>
                          <TableCell>{f.discount_factor.toFixed(5)}</TableCell>
                          <TableCell>{f.implied_rate.toFixed(4)}</TableCell>
                          <TableCell>{f.n_points}</TableCell>
                          <TableCell>{f.r_squared.toFixed(4)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          {result.surface_points.length === 0 ? (
            <Alert variant="destructive">
              <AlertTriangle className="size-4" />
              <AlertTitle>No valid IV points survived cleaning + solving.</AlertTitle>
              <AlertDescription>Try loosening filters.</AlertDescription>
            </Alert>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="size-4 text-primary" />
                  3D Surface: log-moneyness × T × total implied variance
                </CardTitle>
              </CardHeader>
              <CardContent>
                <SurfacePlot points={result.surface_points} />
              </CardContent>
            </Card>
          )}

          <div>
            <h3 className="mb-3 flex items-center gap-2 text-lg font-medium">
              <ShieldAlert className="size-4 text-primary" />
              Arbitrage checks
            </h3>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-2">
                {result.calendar_violations.length === 0 ? (
                  <Alert variant="success">
                    <ShieldCheck className="size-4" />
                    <AlertTitle>No calendar arbitrage violations detected.</AlertTitle>
                  </Alert>
                ) : (
                  <>
                    <Alert variant="destructive">
                      <AlertTriangle className="size-4" />
                      <AlertTitle>
                        {result.calendar_violations.length} calendar arbitrage violation(s) detected
                      </AlertTitle>
                      <AlertDescription>Total variance decreasing in T.</AlertDescription>
                    </Alert>
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>k bucket</TableHead>
                            <TableHead>T earlier</TableHead>
                            <TableHead>T later</TableHead>
                            <TableHead>w earlier</TableHead>
                            <TableHead>w later</TableHead>
                            <TableHead>Violation</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {result.calendar_violations.map((v, i) => (
                            <TableRow key={i}>
                              <TableCell>{v.log_moneyness_bucket.toFixed(3)}</TableCell>
                              <TableCell>{v.T_earlier.toFixed(3)}</TableCell>
                              <TableCell>{v.T_later.toFixed(3)}</TableCell>
                              <TableCell>{v.w_earlier.toFixed(4)}</TableCell>
                              <TableCell>{v.w_later.toFixed(4)}</TableCell>
                              <TableCell>{v.violation_amount.toFixed(4)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </>
                )}
              </div>
              <div className="flex flex-col gap-2">
                {result.butterfly_violations.length === 0 ? (
                  <Alert variant="success">
                    <ShieldCheck className="size-4" />
                    <AlertTitle>No butterfly arbitrage violations detected.</AlertTitle>
                  </Alert>
                ) : (
                  <>
                    <Alert variant="destructive">
                      <AlertTriangle className="size-4" />
                      <AlertTitle>
                        {result.butterfly_violations.length} butterfly arbitrage violation(s) detected
                      </AlertTitle>
                      <AlertDescription>Non-convex call prices.</AlertDescription>
                    </Alert>
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Expiry</TableHead>
                            <TableHead>Strike</TableHead>
                            <TableHead>Convexity value</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {result.butterfly_violations.map((v, i) => (
                            <TableRow key={i}>
                              <TableCell>{v.expiry}</TableCell>
                              <TableCell>{v.strike.toFixed(2)}</TableCell>
                              <TableCell>{v.convexity_value.toFixed(4)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          <Accordion type="multiple">
            <AccordionItem value="raw">
              <AccordionTrigger>Raw solved IV table</AccordionTrigger>
              <AccordionContent>
                <div className="max-h-96 overflow-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Expiry</TableHead>
                        <TableHead>Strike</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>T</TableHead>
                        <TableHead>IV</TableHead>
                        <TableHead>Log-moneyness</TableHead>
                        <TableHead>Total variance</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.surface_points.map((p, i) => (
                        <TableRow key={i}>
                          <TableCell>{p.expiry}</TableCell>
                          <TableCell>{p.strike}</TableCell>
                          <TableCell>{p.option_type}</TableCell>
                          <TableCell>{p.T.toFixed(4)}</TableCell>
                          <TableCell>{p.iv.toFixed(4)}</TableCell>
                          <TableCell>{p.log_moneyness.toFixed(4)}</TableCell>
                          <TableCell>{p.total_variance.toFixed(5)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </>
      )}
    </div>
  );
}
