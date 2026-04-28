import type { Account, Total, Period, AccountingYear, Department } from "@/lib/types";

const BASE_URL = "https://restapi.e-conomic.com";

function getHeaders() {
  return {
    "X-AppSecretToken": process.env.ECONOMIC_APP_SECRET_TOKEN!,
    "X-AgreementGrantToken": process.env.ECONOMIC_AGREEMENT_GRANT_TOKEN!,
    "Content-Type": "application/json",
  };
}

async function apiFetch(url: string, cache: RequestCache = "no-store") {
  const res = await fetch(url, {
    headers: getHeaders(),
    cache,
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
  return apiFetch(`${BASE_URL}/accounts?pagesize=1000`, "force-cache");
}

export async function fetchAccountingYears(): Promise<{ collection: AccountingYear[] }> {
  return apiFetch(`${BASE_URL}/accounting-years`, "force-cache");
}

export async function fetchDepartments(): Promise<{ collection: Department[] }> {
  return apiFetch(`${BASE_URL}/departments`, "force-cache");
}

export async function fetchYearTotals(year: string, departmentNumber?: string): Promise<{ collection: Total[] }> {
  const dept = departmentNumber ? `&departmentNumber=${departmentNumber}` : "";
  return apiFetch(`${BASE_URL}/accounting-years/${year}/totals?pagesize=1000${dept}`);
}

export async function fetchPeriods(year: string): Promise<{ collection: Period[] }> {
  return apiFetch(`${BASE_URL}/accounting-years/${year}/periods`);
}

export async function fetchPeriodTotals(year: string, periodNumber: string, departmentNumber?: string): Promise<{ collection: Total[] }> {
  const dept = departmentNumber ? `&departmentNumber=${departmentNumber}` : "";
  return apiFetch(`${BASE_URL}/accounting-years/${year}/periods/${periodNumber}/totals?pagesize=1000${dept}`);
}
