import type { Account, Total, Period, AccountingYear } from "@/lib/types";

const BASE_URL = "https://restapi.e-conomic.com";

function getHeaders() {
  return {
    "X-AppSecretToken": process.env.ECONOMIC_APP_SECRET_TOKEN!,
    "X-AgreementGrantToken": process.env.ECONOMIC_AGREEMENT_GRANT_TOKEN!,
    "Content-Type": "application/json",
  };
}

async function apiFetch(url: string) {
  const res = await fetch(url, {
    headers: getHeaders(),
    next: { revalidate: 300 },
  });
  if (res.status === 401) throw new Error("Ugyldig API token — tjek environment variables");
  if (res.status === 404) return { collection: [] };
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    console.error(`e-conomic API error ${res.status}: ${body}`);
    throw new Error(`Kunne ikke hente data fra e-conomic (${res.status})`);
  }
  return res.json();
}

export async function fetchAccounts(): Promise<{ collection: Account[] }> {
  return apiFetch(`${BASE_URL}/accounts?pagesize=1000`);
}

export async function fetchAccountingYears(): Promise<{ collection: AccountingYear[] }> {
  return apiFetch(`${BASE_URL}/accounting-years`);
}

export async function fetchYearTotals(year: string): Promise<{ collection: Total[] }> {
  return apiFetch(`${BASE_URL}/accounting-years/${year}/totals?pagesize=1000`);
}

export async function fetchPeriods(year: string): Promise<{ collection: Period[] }> {
  return apiFetch(`${BASE_URL}/accounting-years/${year}/periods`);
}

export async function fetchPeriodTotals(year: string, periodNumber: string): Promise<{ collection: Total[] }> {
  return apiFetch(`${BASE_URL}/accounting-years/${year}/periods/${periodNumber}/totals?pagesize=1000`);
}
