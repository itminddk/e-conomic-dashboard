"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import type { Department } from "@/lib/types";

export default function DepartmentSelector({
  departments,
  selectedDepartment,
}: {
  departments: Department[];
  selectedDepartment: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const p = new URLSearchParams(searchParams.toString());
    if (e.target.value === "") p.delete("department");
    else p.set("department", e.target.value);
    router.push(`${pathname}?${p.toString()}`);
  }

  return (
    <select
      value={selectedDepartment}
      onChange={onChange}
      className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      <option value="">Alle afdelinger</option>
      {departments.map((d) => (
        <option key={d.departmentNumber} value={String(d.departmentNumber)}>
          {d.name}
        </option>
      ))}
    </select>
  );
}
