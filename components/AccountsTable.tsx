import type { Account, Total } from "@/lib/types";
import { formatDKK } from "@/lib/formatting";

const IS_HEADING = new Set(["heading", "headingStart"]);
const IS_TOTAL = new Set(["totalFrom", "sumInterval"]);

export default function AccountsTable({ accounts, totals }: { accounts: Account[]; totals: Total[] }) {
  const totalsMap = new Map(totals.map((t) => [t.account.accountNumber, t.totalInBaseCurrency]));

  // Keep headings always, totals always, regular accounts only if non-zero
  const rows = accounts.filter((a) => {
    if (IS_HEADING.has(a.accountType)) return true;
    if (IS_TOTAL.has(a.accountType)) return true;
    return (totalsMap.get(a.accountNumber) ?? 0) !== 0;
  });

  if (rows.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400">
        Ingen bevægelser at vise for dette regnskabsår.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="font-semibold">Kontoplan</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th className="px-5 py-3 text-left w-24">Kontonr.</th>
              <th className="px-5 py-3 text-left">Navn</th>
              <th className="px-5 py-3 text-right w-40">Beløb</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row) => {
              const amount = totalsMap.get(row.accountNumber);

              if (IS_HEADING.has(row.accountType)) {
                return (
                  <tr key={row.accountNumber} className="bg-gray-50">
                    <td className="px-5 py-2 text-xs text-gray-400 font-mono">{row.accountNumber}</td>
                    <td className="px-5 py-2 font-semibold text-gray-700 uppercase text-xs tracking-wide" colSpan={2}>
                      {row.name}
                    </td>
                  </tr>
                );
              }

              if (IS_TOTAL.has(row.accountType)) {
                return (
                  <tr key={row.accountNumber} className="bg-blue-50 border-t-2 border-blue-100">
                    <td className="px-5 py-2 text-xs text-gray-400 font-mono">{row.accountNumber}</td>
                    <td className="px-5 py-2 font-semibold text-gray-800">{row.name}</td>
                    <td className={`px-5 py-2 text-right font-bold tabular-nums ${
                      amount !== undefined && amount < 0 ? "text-red-600" : "text-gray-900"
                    }`}>
                      {amount !== undefined ? formatDKK(amount, 2) : ""}
                    </td>
                  </tr>
                );
              }

              return (
                <tr key={row.accountNumber} className="hover:bg-gray-50">
                  <td className="px-5 py-2 font-mono text-gray-400 text-xs">{row.accountNumber}</td>
                  <td className="px-5 py-2 pl-8 text-gray-700">{row.name}</td>
                  <td className={`px-5 py-2 text-right tabular-nums ${
                    amount !== undefined && amount < 0 ? "text-red-600" : "text-gray-700"
                  }`}>
                    {amount !== undefined && amount !== 0 ? formatDKK(amount, 2) : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
