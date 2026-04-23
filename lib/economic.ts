const BASE_URL = "https://restapi.e-conomic.com";

function getHeaders() {
  return {
    "X-AppSecretToken": process.env.ECONOMIC_APP_SECRET_TOKEN!,
    "X-AgreementGrantToken": process.env.ECONOMIC_AGREEMENT_GRANT_TOKEN!,
    "Content-Type": "application/json",
  };
}

export async function fetchAccounts() {
  const res = await fetch(`${BASE_URL}/accounts?pagesize=1000`, {
    headers: getHeaders(),
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`e-conomic API fejl: ${res.status}`);
  return res.json();
}

export async function fetchAccountingYears() {
  const res = await fetch(`${BASE_URL}/accounting-years`, {
    headers: getHeaders(),
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`e-conomic API fejl: ${res.status}`);
  return res.json();
}

export async function fetchYearTotals(year: string) {
  const res = await fetch(`${BASE_URL}/accounting-years/${year}/totals`, {
    headers: getHeaders(),
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`e-conomic API fejl: ${res.status}`);
  return res.json();
}
