"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";

interface Period {
  periodNumber: number;
  fromDate: string;
}

const daMonths = ["Januar", "Februar", "Marts", "April", "Maj", "Juni", "Juli", "August", "September", "Oktober", "November", "December"];

export default function PeriodSelector({
  periods,
  selectedPeriod,
}: {
  periods: Period[];
  selectedPeriod: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const params = new URLSearchParams(searchParams.toString());
    if (e.target.value === "") {
      params.delete("period");
    } else {
      params.set("period", e.target.value);
    }
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <select
      value={selectedPeriod}
      onChange={onChange}
      className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      <option value="">Hele året</option>
      {periods.map((p) => {
        const month = new Date(p.fromDate).getMonth();
        return (
          <option key={p.periodNumber} value={String(p.periodNumber)}>
            {daMonths[month]}
          </option>
        );
      })}
    </select>
  );
}
