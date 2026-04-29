"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import type { Period } from "@/lib/types";
import { DA_MONTHS } from "@/lib/formatting";

export default function PeriodSelector({ periods, selectedPeriod }: { periods: Period[]; selectedPeriod: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const p = new URLSearchParams(searchParams.toString());
    if (e.target.value === "") p.delete("period");
    else p.set("period", e.target.value);
    router.push(`${pathname}?${p.toString()}`);
    router.refresh();
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
        const label = month >= 0 && month <= 11 ? DA_MONTHS[month] : p.fromDate;
        return (
          <option key={p.periodNumber} value={String(p.periodNumber)}>
            {label}
          </option>
        );
      })}
    </select>
  );
}
