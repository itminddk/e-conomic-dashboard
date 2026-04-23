export interface Account {
  accountNumber: number;
  name: string;
  accountType: "profitAndLoss" | "status" | "heading" | "headingStart" | "sumInterval" | "totalFrom";
  debitCredit: "debit" | "credit";
  balance: number;
}

export interface Total {
  totalInBaseCurrency: number;
  account: { accountNumber: number };
  fromDate: string;
  toDate: string;
}

export interface Period {
  periodNumber: number;
  fromDate: string;
  toDate: string;
  barred?: boolean;
}

export interface AccountingYear {
  year: string;
  fromDate: string;
  toDate: string;
  closed: boolean;
}
