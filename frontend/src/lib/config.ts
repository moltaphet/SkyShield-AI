import { localnet, studionet, testnetAsimov, testnetBradbury } from "genlayer-js/chains";

/**
 * Central runtime configuration, sourced from public env vars.
 * See `.env.local.example` for the available settings.
 *
 * NEXT_PUBLIC_* values are inlined at build time, so they are available during
 * both server-side rendering and client-side execution. We normalize them
 * defensively (trim + strip any surrounding quotes) so a value written as
 * NEXT_PUBLIC_CONTRACT_ADDRESS="0x..." is read identically to the unquoted form.
 */

function readEnv(value: string | undefined, fallback = ""): string {
  if (!value) return fallback;
  return value.trim().replace(/^["']|["']$/g, "");
}

export const CONTRACT_ADDRESS = readEnv(
  process.env.NEXT_PUBLIC_CONTRACT_ADDRESS,
) as `0x${string}`;

const CHAINS = {
  studionet,
  localnet,
  testnetAsimov,
  testnetBradbury,
} as const;

export type ChainName = keyof typeof CHAINS;

const requestedChain = readEnv(
  process.env.NEXT_PUBLIC_GENLAYER_CHAIN,
  "studionet",
) as ChainName;

export const activeChain = CHAINS[requestedChain] ?? studionet;
export const activeChainName: ChainName = CHAINS[requestedChain]
  ? requestedChain
  : "studionet";

/** Atto scale: every money value in the contract is `value * 10 ** 18`. */
export const TOKEN_DECIMALS = 18;

/** Display symbol for the staked asset (UI only). */
export const TOKEN_SYMBOL = "GEN";

/** True when a real contract address has been configured. */
export const isContractConfigured =
  CONTRACT_ADDRESS.length === 42 &&
  CONTRACT_ADDRESS !== "0x0000000000000000000000000000000000000000";
