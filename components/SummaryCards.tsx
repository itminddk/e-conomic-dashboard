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
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export default function SummaryCards({ totals }: { totals: Total[] }) {
  const totalAssets = totals
    .filter((t) => t.accountType === "status" && t.closingBalance > 0)
    .reduce((sum, t) => sum + t.closingBalance, 0);

  const totalRevenue = totals
    .filter((t) => t.accountType === "profitAndLoss" && t.closingBalance < 0)
    .reduce((sum, t) => sum + Math.abs(t.closingBalance), 0);

  const totalExpenses = totals
    .filter((t) => t.accountType === "profitAndLoss" && t.closingBalance > 0)
    .reduce((sum, t) => sum + t.closingBalance, 0);

  const result = totalRevenue - totalExpenses;

  const cards = [
    { label: "Omsætning", value: totalRevenue, color: "text-green-600" },
    { label: "Omkostninger", value: totalExpenses, color: "text-red-600" },
    { label: "Resultat", value: result, color: result >= 0 ? "text-green-600" : "text-red-600" },
    { label: "Aktiver", value: totalAssets, color: "text-blue-600" },
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
