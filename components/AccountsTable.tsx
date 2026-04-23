interface Account {
  accountNumber: number;
  name: string;
  accountType: string;
}

interface Total {
  accountNumber: number;
  accountName: string;
  closingBalance: number;
  openingBalance: number;
  accountType?: string;
}

function formatDKK(amount: number) {
  return new Intl.NumberFormat("da-DK", {
    style: "currency",
    currency: "DKK",
    minimumFractionDigits: 2,
  }).format(amount);
}

export default function AccountsTable({
  accounts,
  totals,
}: {
  accounts: Account[];
  totals: Total[];
}) {
  const totalsMap = new Map(totals.map((t) => [t.accountNumber, t]));

  const rows = accounts
    .map((a) => ({ ...a, total: totalsMap.get(a.accountNumber) }))
    .filter((a) => a.total && a.total.closingBalance !== 0);

  if (rows.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400">
        Ingen kontodata at vise for dette regnskabsår.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="font-semibold">Kontoplan med saldi</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th className="px-5 py-3 text-left">Kontonr.</th>
              <th className="px-5 py-3 text-left">Navn</th>
              <th className="px-5 py-3 text-left">Type</th>
              <th className="px-5 py-3 text-right">Primo</th>
              <th className="px-5 py-3 text-right">Ultimo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row) => (
              <tr key={row.accountNumber} className="hover:bg-gray-50">
                <td className="px-5 py-3 font-mono text-gray-500">{row.accountNumber}</td>
                <td className="px-5 py-3 font-medium">{row.name}</td>
                <td className="px-5 py-3 text-gray-500">{row.accountType}</td>
                <td className="px-5 py-3 text-right tabular-nums">
                  {formatDKK(row.total?.openingBalance ?? 0)}
                </td>
                <td
                  className={`px-5 py-3 text-right tabular-nums font-medium ${
                    (row.total?.closingBalance ?? 0) < 0
                      ? "text-red-600"
                      : "text-gray-900"
                  }`}
                >
                  {formatDKK(row.total?.closingBalance ?? 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
