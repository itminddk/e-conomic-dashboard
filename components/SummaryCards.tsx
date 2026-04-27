import type { Account, Total } from "@/lib/types";
import { formatDKK } from "@/lib/formatting";
import { computePLSummary } from "@/lib/computeTotals";

export default function SummaryCards({ accounts, totals }: { accounts: Account[]; totals: Total[] }) {
  const { revenue, expenses, result } = computePLSummary(accounts, totals);

  const cards = [
    { label: "Omsætning", value: revenue, color: "text-gray-900" },
    { label: "Omkostninger", value: expenses, color: "text-gray-900" },
    { label: "Resultat", value: result, color: result >= 0 ? "text-green-600" : "text-red-600" },
  ];

  return (
    <div className="grid grid-cols-3 gap-4">
      {cards.map((card) => (
        <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">{card.label}</p>
          <p className={`text-xl font-bold mt-1 ${card.color}`}>{formatDKK(card.value)}</p>
        </div>
      ))}
    </div>
  );
}
