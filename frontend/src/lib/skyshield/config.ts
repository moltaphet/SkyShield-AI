/**
 * SkyShield AI runtime configuration.
 *
 * SkyShield reuses the shared GenLayer chain selection (see `../config`) but
 * targets its own deployed contract address, supplied via
 * NEXT_PUBLIC_SKYSHIELD_CONTRACT_ADDRESS. When no address is set the dashboard
 * runs in a self-contained simulation mode so the UI is fully interactive
 * without a live deployment.
 */

function readEnv(value: string | undefined, fallback = ""): string {
  if (!value) return fallback;
  return value.trim().replace(/^["']|["']$/g, "");
}

/** Deployed SkyShield AI contract; overridable via env for other networks. */
const DEFAULT_CONTRACT_ADDRESS = "0x43050A476485547450Aa80A4Bf059D17CE17CC28";

export const SKYSHIELD_CONTRACT_ADDRESS = readEnv(
  process.env.NEXT_PUBLIC_SKYSHIELD_CONTRACT_ADDRESS,
  DEFAULT_CONTRACT_ADDRESS,
) as `0x${string}`;

/** True once a real SkyShield contract address has been configured. */
export const isSkyShieldConfigured =
  SKYSHIELD_CONTRACT_ADDRESS.length === 42 &&
  SKYSHIELD_CONTRACT_ADDRESS !== "0x0000000000000000000000000000000000000000";

/** Display symbol for the underwriting asset (UI only). */
export const TOKEN_SYMBOL = "GEN";

// --------------------------------------------------------------------------- //
// Economic constants mirrored from contracts/sky_shield_ai.py so the in-app    //
// premium preview reproduces the on-chain pricing math exactly.                //
// --------------------------------------------------------------------------- //
export const ATTO = 10n ** 18n;
export const BPS_DENOMINATOR = 10_000n;

/** Protocol risk margin added on top of fair odds (30%). */
export const LOADING_BPS = 3_000n;
/** Premium floor in atto GEN. */
export const MIN_PREMIUM_ATTO = 1n * ATTO;
/** Coverage underwritten by a single base policy on-chain (1000 GEN). */
export const BASE_COVERAGE_ATTO = 1_000n * ATTO;
