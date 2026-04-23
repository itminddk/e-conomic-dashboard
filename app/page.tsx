import { fetchAccountingYears, fetchYearTotals, fetchAccounts } from "@/lib/economic";
import AccountsTable from "@/components/AccountsTable";
import SummaryCards from "@/components/SummaryCards";
import YearSelector from "@/components/YearSelector";

interface SearchParams {
  year?: string;
}

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  let years: string[] = [];
  let selectedYear = "";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let totals: any[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let accounts: any[] = [];
  let error = "";

  try {
    const yearsData = await fetchAccountingYears();
    years = (yearsData.collection ?? []).map(
      (y: { year: string }) => y.year
    );
    selectedYear = params.year ?? years[years.length - 1] ?? "";

    const [totalsData, accountsData] = await Promise.all([
      selectedYear ? fetchYearTotals(selectedYear) : Promise.resolve({ collection: [] }),
      fetchAccounts(),
    ]);

    totals = totalsData.collection ?? [];
    accounts = accountsData.collection ?? [];
  } catch (err) {
    error = String(err);
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        <strong>Fejl:</strong> {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Regnskabsoverblik</h2>
          <p className="text-gray-500 text-sm mt-1">Data fra e-conomic</p>
        </div>
        <YearSelector years={years} selectedYear={selectedYear} />
      </div>

      <SummaryCards totals={totals} />
      <AccountsTable accounts={accounts} totals={totals} />
    </div>
  );
}
