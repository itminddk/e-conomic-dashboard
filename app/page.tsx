export const dynamic = "force-dynamic";

import { fetchAccountingYears, fetchYearTotals, fetchAccounts, fetchPeriods, fetchPeriodTotals, fetchDepartments } from "@/lib/economic";
import type { Account, Total, Period, Department } from "@/lib/types";
import AccountsTable from "@/components/AccountsTable";
import SummaryCards from "@/components/SummaryCards";
import YearSelector from "@/components/YearSelector";
import PeriodSelector from "@/components/PeriodSelector";
import DepartmentSelector from "@/components/DepartmentSelector";
import RefreshButton from "@/components/RefreshButton";

const VALID_YEAR = /^\d{4}$/;
const VALID_PERIOD = /^\d+$/;
const VALID_DEPT = /^\d+$/;

interface SearchParams {
  year?: string;
  period?: string;
  department?: string;
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
  let departments: Department[] = [];
  let selectedDepartment = "";
  let totals: Total[] = [];
  let accounts: Account[] = [];
  let error = "";

  const rawYear = params.year ?? "";
  const rawPeriod = params.period ?? "";
  const rawDept = params.department ?? "";

  if (rawYear && !VALID_YEAR.test(rawYear)) {
    error = "Ugyldigt år i URL";
  } else if (rawPeriod && !VALID_PERIOD.test(rawPeriod)) {
    error = "Ugyldig periode i URL";
  } else if (rawDept && !VALID_DEPT.test(rawDept)) {
    error = "Ugyldig afdeling i URL";
  } else {
    try {
      const yearsData = await fetchAccountingYears();
      years = yearsData.collection.map((y) => y.year);
      selectedYear = rawYear || years[years.length - 1] || "";
      selectedPeriod = rawPeriod;
      selectedDepartment = rawDept;

      const [periodsData, totalsData, accountsData, departmentsData] = await Promise.all([
        selectedYear ? fetchPeriods(selectedYear) : Promise.resolve({ collection: [] as Period[] }),
        selectedYear && selectedPeriod
          ? fetchPeriodTotals(selectedYear, selectedPeriod, selectedDepartment || undefined)
          : selectedYear
          ? fetchYearTotals(selectedYear, selectedDepartment || undefined)
          : Promise.resolve({ collection: [] as Total[] }),
        fetchAccounts(),
        fetchDepartments(),
      ]);

      periods = periodsData.collection;
      totals = totalsData.collection;
      accounts = accountsData.collection;
      departments = departmentsData.collection.filter((d) => !d.barred);
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold">Regnskabsoverblik</h2>
          <p className="text-gray-500 text-sm mt-0.5">Data fra e-conomic</p>
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <YearSelector years={years} selectedYear={selectedYear} />
          <PeriodSelector periods={periods} selectedPeriod={selectedPeriod} />
          <DepartmentSelector departments={departments} selectedDepartment={selectedDepartment} />
          <RefreshButton />
        </div>
      </div>

      <SummaryCards accounts={accounts} totals={totals} />
      <AccountsTable accounts={accounts} totals={totals} />
    </div>
  );
}
