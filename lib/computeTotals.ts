import type { Account, Total } from "@/lib/types";

/**
 * e-conomic returns 0 for all totalFrom/sumInterval accounts.
 * This function calculates them from the underlying profitAndLoss/status accounts.
 *
 * Two patterns:
 *   Sub-group total: totalFrom after regular accounts → sums those accounts
 *   Grand total:     totalFrom after another totalFrom → sums all preceding sub-group totals
 */
export function buildTotalsMap(accounts: Account[], totals: Total[]): Map<number, number> {
  const apiMap = new Map(totals.map((t) => [t.account.accountNumber, t.totalInBaseCurrency]));
  const result = new Map(apiMap);
  let sectionSum = 0;
  let cumulativeSum = 0;
  let hasDirectAccounts = false;

  for (const acc of accounts) {
    switch (acc.accountType) {
      case "headingStart":
        sectionSum = 0;
        cumulativeSum = 0;
        hasDirectAccounts = false;
        break;
      case "heading":
        break;
      case "profitAndLoss":
      case "status":
        sectionSum += apiMap.get(acc.accountNumber) ?? 0;
        hasDirectAccounts = true;
        break;
      case "totalFrom":
      case "sumInterval": {
        const value = hasDirectAccounts ? sectionSum : cumulativeSum;
        if (hasDirectAccounts) cumulativeSum += value;
        else cumulativeSum = value;
        result.set(acc.accountNumber, value);
        sectionSum = 0;
        hasDirectAccounts = false;
        break;
      }
    }
  }
  return result;
}

export interface PLSummary {
  revenue: number;      // Omsætning (abs of first P&L grand total)
  expenses: number;     // Omkostninger = revenue - result
  result: number;       // Resultat (last P&L grand total)
}

/**
 * Computes P&L summary values by finding the first and last grand totals
 * in the P&L (profitAndLoss) section of the account plan.
 */
export function computePLSummary(accounts: Account[], totals: Total[]): PLSummary {
  const apiMap = new Map(totals.map((t) => [t.account.accountNumber, t.totalInBaseCurrency]));
  const grandTotals: number[] = [];
  let sectionSum = 0;
  let cumulativeSum = 0;
  let hasDirectAccounts = false;
  let lastWasPL = true;

  for (const acc of accounts) {
    switch (acc.accountType) {
      case "headingStart":
        sectionSum = 0;
        cumulativeSum = 0;
        hasDirectAccounts = false;
        break;
      case "heading":
        break;
      case "profitAndLoss":
        sectionSum += apiMap.get(acc.accountNumber) ?? 0;
        hasDirectAccounts = true;
        lastWasPL = true;
        break;
      case "status":
        sectionSum += apiMap.get(acc.accountNumber) ?? 0;
        hasDirectAccounts = true;
        lastWasPL = false;
        break;
      case "totalFrom":
      case "sumInterval": {
        const isGrand = !hasDirectAccounts;
        const value = hasDirectAccounts ? sectionSum : cumulativeSum;
        if (hasDirectAccounts) cumulativeSum += value;
        else cumulativeSum = value;
        if (isGrand && lastWasPL) grandTotals.push(value);
        sectionSum = 0;
        hasDirectAccounts = false;
        break;
      }
    }
  }

  const revenue = grandTotals.length > 0 ? Math.abs(grandTotals[0]) : 0;
  const result = grandTotals.length > 0 ? grandTotals[grandTotals.length - 1] : 0;
  const expenses = revenue - result;
  return { revenue, expenses, result };
}
