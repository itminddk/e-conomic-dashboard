interface Account {
  accountNumber: number;
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
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export default function SummaryCards({
  accounts,
  totals,
}: {
  accounts: Account[];
  totals: Total[];
}) {
  const accountsMap = new Map(accounts.map((a) => [a.accountNumber, a]));

  let revenue = 0;
  let expenses = 0;
  let assets = 0;

  for (const t of totals) {
    const total = t.totalInBaseCurrency;
    if (total === 0) continue;
    const account = accountsMap.get(t.account.accountNumber);
    if (!account) continue;

    if (account.accountType === "profitAndLoss") {
      if (account.debitCredit === "credit") revenue += Math.abs(total);
      else expenses += Math.abs(total);
    } else if (account.accountType === "status" && account.debitCredit === "debit") {
      assets += total;
    }
  }

  const result = revenue - expenses;

  const cards = [
    { label: "Omsætning", value: revenue, color: "text-green-600" },
    { label: "Omkostninger", value: expenses, color: "text-red-600" },
    { label: "Resultat", value: result, color: result >= 0 ? "text-green-600" : "text-red-600" },
    { label: "Aktiver", value: assets, color: "text-blue-600" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">{card.label}</p>
          <p className={`text-xl font-bold mt-1 ${card.color}`}>
            {formatDKK(card.value)}
          </p>
        </div>
      ))}
    </div>
  );
}
