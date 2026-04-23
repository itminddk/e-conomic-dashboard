import { NextResponse } from "next/server";
import { fetchAccounts } from "@/lib/economic";

export async function GET() {
  try {
    const data = await fetchAccounts();
    return NextResponse.json(data);
  } catch (err) {
    console.error("GET /api/accounts:", err);
    return NextResponse.json({ error: "Intern serverfejl" }, { status: 500 });
  }
}
