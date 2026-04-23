import { fetchAccountingYears, fetchYearTotals, fetchAccounts, fetchPeriods, fetchPeriodTotals } from "@/lib/economic";
import type { Account, Total, Period } from "@/lib/types";
import AccountsTable from "@/components/AccountsTable";
import SummaryCards from "@/components/SummaryCards";
import YearSelector from "@/components/YearSelector";
import PeriodSelector from "@/components/PeriodSelector";

const VALID_YEAR = /^\d{4}$/;
const VALID_PERIOD = /^\d+$/;

interface SearchParams {
  year?: string;
  period?: string;
}

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  let years: string[] = [];
  let selectedYear = "";
  let periods: Period[] = [];
  let selectedPeriod = "";
  let totals: Total[] = [];
  let accounts: Account[] = [];
  let error = "";

  const rawYear = params.year ?? "";
  const rawPeriod = params.period ?? "";

  if (rawYear && !VALID_YEAR.test(rawYear)) {
    error = "Ugyldigt år i URL";
  } else if (rawPeriod && !VALID_PERIOD.test(rawPeriod)) {
    error = "Ugyldig periode i URL";
  } else {
    try {
      const yearsData = await fetchAccountingYears();
      years = yearsData.collection.map((y) => y.year);
      selectedYear = rawYear || years[years.length - 1] || "";
      selectedPeriod = rawPeriod;

      const [periodsData, totalsData, accountsData] = await Promise.all([
        selectedYear ? fetchPeriods(selectedYear) : Promise.resolve({ collection: [] as Period[] }),
        selectedYear && selectedPeriod
          ? fetchPeriodTotals(selectedYear, selectedPeriod)
          : selectedYear
          ? fetchYearTotals(selectedYear)
          : Promise.resolve({ collection: [] as Total[] }),
        fetchAccounts(),
      ]);

      periods = periodsData.collection;
      totals = totalsData.collection;
      accounts = accountsData.collection;
    } catch (err) {
      error = err instanceof Error ? err.message : "Ukendt fejl";
    }
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
        <div className="flex gap-2">
          <YearSelector years={years} selectedYear={selectedYear} />
          <PeriodSelector periods={periods} selectedPeriod={selectedPeriod} />
        </div>
      </div>

      <SummaryCards accounts={accounts} totals={totals} />
      <AccountsTable accounts={accounts} totals={totals} />
    </div>
  );
}
