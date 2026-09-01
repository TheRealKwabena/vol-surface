/**
 * Spot-form Black-Scholes-Merton price + Greeks, ported line-for-line from
 * vol_surface/pricing/black_scholes.py (bsm_price, bsm_greeks) so the Greeks
 * Explorer tab can run entirely client-side with zero backend round-trips.
 *
 * scipy.stats.norm isn't available in JS, so normCdf/normPdf are implemented
 * from scratch below (Abramowitz-Stegun 7.1.26 erf approximation, ~1.5e-7
 * max error -- fine for a UI displaying 4-5 decimal places).
 */

export type OptionType = "call" | "put";

export interface Greeks {
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
  rho: number;
  vanna: number;
  volga: number;
  charm: number;
}

const EPS = 1e-12;

function safeT(T: number): number {
  return Math.max(T, EPS);
}

function safeSigma(sigma: number): number {
  return Math.max(sigma, EPS);
}

function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * ax);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax);
  return sign * y;
}

function normCdf(x: number): number {
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

function normPdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

function d1d2Spot(S: number, K: number, T: number, r: number, q: number, sigma: number): [number, number] {
  const Ts = safeT(T);
  const sigmaS = safeSigma(sigma);
  const d1 = (Math.log(S / K) + (r - q + 0.5 * sigmaS * sigmaS) * Ts) / (sigmaS * Math.sqrt(Ts));
  const d2 = d1 - sigmaS * Math.sqrt(Ts);
  return [d1, d2];
}

export function bsmPrice(
  S: number,
  K: number,
  T: number,
  r: number,
  q: number,
  sigma: number,
  optionType: OptionType = "call",
): number {
  const [d1, d2] = d1d2Spot(S, K, T, r, q, sigma);
  const discR = Math.exp(-r * T);
  const discQ = Math.exp(-q * T);

  if (optionType === "call") {
    return S * discQ * normCdf(d1) - K * discR * normCdf(d2);
  }
  return K * discR * normCdf(-d2) - S * discQ * normCdf(-d1);
}

export function bsmGreeks(
  S: number,
  K: number,
  T: number,
  r: number,
  q: number,
  sigma: number,
  optionType: OptionType = "call",
): Greeks {
  const Ts = safeT(T);
  const sigmaS = safeSigma(sigma);
  const [d1, d2] = d1d2Spot(S, K, Ts, r, q, sigmaS);
  const discR = Math.exp(-r * Ts);
  const discQ = Math.exp(-q * Ts);
  const pdfD1 = normPdf(d1);
  const sqrtT = Math.sqrt(Ts);

  const gamma = (discQ * pdfD1) / (S * sigmaS * sqrtT);
  const vega = S * discQ * pdfD1 * sqrtT;
  const vanna = (-discQ * pdfD1 * d2) / sigmaS;
  const volga = (vega * d1 * d2) / sigmaS;

  let delta: number;
  let theta: number;
  let rho: number;
  let charm: number;

  if (optionType === "call") {
    delta = discQ * normCdf(d1);
    theta =
      (-S * discQ * pdfD1 * sigmaS) / (2 * sqrtT) - r * K * discR * normCdf(d2) + q * S * discQ * normCdf(d1);
    rho = K * Ts * discR * normCdf(d2);
    charm =
      q * discQ * normCdf(d1) -
      (discQ * pdfD1 * (2 * (r - q) * Ts - d2 * sigmaS * sqrtT)) / (2 * Ts * sigmaS * sqrtT);
  } else {
    delta = -discQ * normCdf(-d1);
    theta =
      (-S * discQ * pdfD1 * sigmaS) / (2 * sqrtT) + r * K * discR * normCdf(-d2) - q * S * discQ * normCdf(-d1);
    rho = -K * Ts * discR * normCdf(-d2);
    charm =
      -q * discQ * normCdf(-d1) -
      (discQ * pdfD1 * (2 * (r - q) * Ts - d2 * sigmaS * sqrtT)) / (2 * Ts * sigmaS * sqrtT);
  }

  return { delta, gamma, vega, theta, rho, vanna, volga, charm };
}
