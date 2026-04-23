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

  if (res.status === 401) throw new Error("Ugyldig API token (401) — tjek dine tokens i Hostinger");
  if (res.status === 404) return { collection: [] };
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`e-conomic API fejl: ${res.status} ${body}`);
  }
  return res.json();
}

export async function fetchAccounts() {
  return apiFetch(`${BASE_URL}/accounts?pagesize=1000`);
}

export async function fetchAccountingYears() {
  return apiFetch(`${BASE_URL}/accounting-years`);
}

export async function fetchYearTotals(year: string) {
  return apiFetch(`${BASE_URL}/accounting-years/${year}/totals`);
}
