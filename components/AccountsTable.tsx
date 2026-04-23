interface Account {
  accountNumber: number;
  name: string;
  accountType: string;
  debitCredit: string;
}

interface Total {
  totalInBaseCurrency: number;
  account: { accountNumber: number };
}

function formatDKK(amount: number) {
  return new Intl.NumberFormat("da-DK", {
    style: "currency",
    currency: "DKK",
    minimumFractionDigits: 2,
  }).format(amount);
}

const typeLabels: Record<string, string> = {
  profitAndLoss: "Resultat",
  status: "Balance",
  heading: "Overskrift",
  sumInterval: "Sum",
  totalFrom: "Total",
};

export default function AccountsTable({
  accounts,
  totals,
}: {
  accounts: Account[];
  totals: Total[];
}) {
  const totalsMap = new Map(
    totals.map((t) => [t.account.accountNumber, t.totalInBaseCurrency])
  );

  const rows = accounts
    .filter((a) => a.accountType !== "heading")
    .map((a) => ({ ...a, total: totalsMap.get(a.accountNumber) ?? 0 }))
    .filter((a) => a.total !== 0);

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
        <h3 className="font-semibold">Kontoplan med bevægelser</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th className="px-5 py-3 text-left">Kontonr.</th>
              <th className="px-5 py-3 text-left">Navn</th>
              <th className="px-5 py-3 text-left">Type</th>
              <th className="px-5 py-3 text-right">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row) => (
              <tr key={row.accountNumber} className="hover:bg-gray-50">
                <td className="px-5 py-3 font-mono text-gray-500">{row.accountNumber}</td>
                <td className="px-5 py-3 font-medium">{row.name}</td>
                <td className="px-5 py-3 text-gray-500">
                  {typeLabels[row.accountType] ?? row.accountType}
                </td>
                <td
                  className={`px-5 py-3 text-right tabular-nums font-medium ${
                    row.total < 0 ? "text-red-600" : "text-gray-900"
                  }`}
                >
                  {formatDKK(row.total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
