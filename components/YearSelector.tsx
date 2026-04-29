"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";

export default function YearSelector({
  years,
  selectedYear,
}: {
  years: string[];
  selectedYear: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("year", e.target.value);
    params.delete("period");
    router.push(`${pathname}?${params.toString()}`);
    router.refresh();
  }

  return (
    <select
      value={selectedYear}
      onChange={onChange}
      className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {years.map((y) => (
        <option key={y} value={y}>
          {y}
        </option>
      ))}
    </select>
  );
}
