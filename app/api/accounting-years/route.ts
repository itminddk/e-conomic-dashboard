import { NextResponse } from "next/server";
import { fetchAccountingYears } from "@/lib/economic";

export async function GET() {
  try {
    const data = await fetchAccountingYears();
    return NextResponse.json(data);
  } catch (err) {
    console.error("GET /api/accounting-years:", err);
    return NextResponse.json({ error: "Intern serverfejl" }, { status: 500 });
  }
}
