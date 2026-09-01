export interface CleaningReport {
  rows_in: number;
  rows_out: number;
  rows_dropped: number;
  filters: Record<string, number>;
}

export interface ForwardFit {
  expiry: string;
  T: number;
  forward: number;
  discount_factor: number;
  implied_rate: number;
  n_points: number;
  r_squared: number;
}

export interface SurfacePoint {
  expiry: string;
  T: number;
  strike: number;
  option_type: "call" | "put";
  bid: number | null;
  ask: number | null;
  last: number | null;
  volume: number | null;
  open_interest: number | null;
  implied_vol_yf: number | null;
  underlying_price: number | null;
  mid: number;
  forward: number;
  discount_factor: number;
  iv: number;
  iv_converged: boolean;
  iv_method: string;
  log_moneyness: number;
  total_variance: number;
}

export interface CalendarViolation {
  log_moneyness_bucket: number;
  T_earlier: number;
  T_later: number;
  w_earlier: number;
  w_later: number;
  violation_amount: number;
}

export interface ButterflyViolation {
  expiry: string;
  strike: number;
  convexity_value: number;
}

export interface VolSurfaceRequest {
  ticker: string;
  max_expiries: number;
  max_spread_frac: number;
  require_volume_or_oi: boolean;
}

export interface VolSurfaceResponse {
  ticker: string;
  cleaning_report: CleaningReport;
  forward_fits: ForwardFit[];
  convergence_rate: number;
  surface_points: SurfacePoint[];
  calendar_violations: CalendarViolation[];
  butterfly_violations: ButterflyViolation[];
}
